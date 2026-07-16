import asyncio
import io

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from app.core import store
from app.models.manifest import SemanticRole
from app.services import append as ap


def _mk_upload(tmp_path, monkeypatch, rows=None):
    """A tiny uploaded dataset: one table 'cases' with an id + category column."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    import duckdb
    from app.services.profiler import build_manifest
    df = rows if rows is not None else pd.DataFrame(
        {"fir_no": ["A1", "A2", "A3"], "crime_group": ["Theft", "Theft", "Assault"]})
    con = duckdb.connect(); con.register("s", df)
    con.execute('CREATE TABLE "cases" AS SELECT * FROM s')
    out = store.table_path("d1", "cases"); out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY \"cases\" TO '{out}' (FORMAT PARQUET)")
    m = build_manifest(con, ["cases"], name="d1", dataset_id="d1")
    m.source = "upload"
    store.save_manifest(m)
    return m


def test_append_adds_and_dedupes_by_id(monkeypatch, tmp_path):
    _mk_upload(tmp_path, monkeypatch)
    inc = pd.DataFrame({"fir_no": ["A3", "A4", "A5"], "crime_group": ["Theft", "Cyber", "Cyber"]})
    res = ap.append_tables("d1", {"cases": inc}, files=["update.xlsx"])
    t = res["tables"][0]
    assert t["added"] == 2 and t["duplicates_skipped"] == 1 and not t["new_table"]
    m = store.load_manifest("d1")
    assert m.table("cases").row_count == 5
    assert m.updated_at is not None
    assert ap.read_log("d1")[0]["action"] == "append"


def test_append_aligns_columns_and_preserves_roles(monkeypatch, tmp_path):
    m = _mk_upload(tmp_path, monkeypatch)
    # pin a role, then append a frame missing crime_group + carrying an extra col
    m.table("cases").columns[1].semantic_role = SemanticRole.CATEGORY
    store.save_manifest(m)
    inc = pd.DataFrame({"fir_no": ["B1"], "unexpected": ["x"]})
    res = ap.append_tables("d1", {"cases": inc}, files=["u.xlsx"])
    assert res["tables"][0]["extras_ignored"] == 1
    m2 = store.load_manifest("d1")
    assert m2.table("cases").columns[1].semantic_role == SemanticRole.CATEGORY  # role preserved
    assert m2.table("cases").row_count == 4


def test_append_new_table_is_added_and_linked(monkeypatch, tmp_path):
    _mk_upload(tmp_path, monkeypatch)
    acc = pd.DataFrame({"accused_id": ["X1", "X2"], "fir_no": ["A1", "A2"],
                        "name": ["P Kumar", "R Gowda"]})
    res = ap.append_tables("d1", {"accused": acc}, files=["accused.xlsx"])
    assert res["tables"][0]["new_table"] is True
    m = store.load_manifest("d1")
    assert m.table("accused") is not None
    assert any(r.from_table == "accused" and r.to_table == "cases" for r in m.relations)


def test_seed_dataset_is_readonly(monkeypatch, tmp_path):
    m = _mk_upload(tmp_path, monkeypatch)
    m.source = "seed"
    store.save_manifest(m)
    with pytest.raises(ap.ReadOnlyDatasetError):
        ap.append_tables("d1", {"cases": pd.DataFrame({"fir_no": ["Z"]})}, files=["z.csv"])


def test_fallback_seed_ids_are_readonly(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    import duckdb
    from app.services.profiler import build_manifest
    df = pd.DataFrame({"fir_no": ["A1"]})
    con = duckdb.connect(); con.register("s", df)
    con.execute('CREATE TABLE "t" AS SELECT * FROM s')
    out = store.table_path("ksp-crime", "t"); out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY \"t\" TO '{out}' (FORMAT PARQUET)")
    m = build_manifest(con, ["t"], name="x", dataset_id="ksp-crime")  # old manifest: no source field stamp
    store.save_manifest(m)
    with pytest.raises(ap.ReadOnlyDatasetError):
        ap.append_tables("ksp-crime", {"t": df}, files=["z.csv"])


def test_row_hash_dedupe_without_id(monkeypatch, tmp_path):
    # table whose only column is a low-cardinality category -> no ID role
    df = pd.DataFrame({"category": ["a", "b", "c", "a", "b", "c"]})
    _mk_upload(tmp_path, monkeypatch, rows=df.rename(columns={"category": "kind"}))
    inc = pd.DataFrame({"kind": ["a", "zz"]})
    res = ap.append_tables("d1", {"cases": inc}, files=["u.csv"])
    assert res["tables"][0]["added"] == 1 and res["tables"][0]["duplicates_skipped"] == 1


def test_renamed_file_with_same_columns_appends_not_duplicates(monkeypatch, tmp_path):
    _mk_upload(tmp_path, monkeypatch)
    # different table name, identical column set -> Jaccard 1.0 >= 0.8 -> appends to 'cases'
    inc = pd.DataFrame({"fir_no": ["N1", "N2"], "crime_group": ["Cyber", "Cyber"]})
    res = ap.append_tables("d1", {"cases_july_update": inc}, files=["Cases July Update.xlsx"])
    t = res["tables"][0]
    assert t["name"] == "cases" and t["added"] == 2 and not t["new_table"]
    m = store.load_manifest("d1")
    assert m.table("cases").row_count == 5 and m.table("cases_july_update") is None


# ---------------------------------------------------------------------------
# Router-level tests: POST /api/ingest/{dataset_id}/append
# ---------------------------------------------------------------------------

def _upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename)


def test_append_router_happy_path(monkeypatch, tmp_path):
    from app.routers import ingest as ingest_router
    _mk_upload(tmp_path, monkeypatch)
    csv_bytes = b"fir_no,crime_group\nA4,Cyber\nA5,Cyber\n"
    result = asyncio.run(
        ingest_router.append_to_dataset("d1", files=[_upload("update.csv", csv_bytes)])
    )
    t = result["tables"][0]
    assert t["added"] == 2 and t["duplicates_skipped"] == 0 and not t["new_table"]
    m = store.load_manifest("d1")
    assert m.table("cases").row_count == 5


def test_append_router_unknown_dataset_404(monkeypatch, tmp_path):
    from app.routers import ingest as ingest_router
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    csv_bytes = b"fir_no\nZ1\n"
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.append_to_dataset("nope", files=[_upload("u.csv", csv_bytes)])
        )
    assert exc_info.value.status_code == 404


def test_append_router_readonly_dataset_400(monkeypatch, tmp_path):
    from app.routers import ingest as ingest_router
    m = _mk_upload(tmp_path, monkeypatch)
    m.source = "seed"
    store.save_manifest(m)
    csv_bytes = b"fir_no,crime_group\nZ1,Theft\n"
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.append_to_dataset("d1", files=[_upload("u.csv", csv_bytes)])
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "This demo dataset is read-only — upload a copy from Home to extend it."
    )


# ---------------------------------------------------------------------------
# Router-level tests: GET /api/datasets/{dataset_id}/composition
# ---------------------------------------------------------------------------

def test_composition_returns_totals_and_history(monkeypatch, tmp_path):
    from app.routers import datasets as datasets_router
    _mk_upload(tmp_path, monkeypatch)
    inc = pd.DataFrame({"fir_no": ["A9"], "crime_group": ["Cyber"]})
    ap.append_tables("d1", {"cases": inc}, files=["update.xlsx"])

    result = datasets_router.composition("d1")
    assert result["id"] == "d1"
    assert result["total_rows"] == 4
    assert result["tables"] == [{"name": "cases", "row_count": 4, "n_columns": 2}]
    assert result["history"][0]["action"] == "append"  # newest first
    assert "created_at" in result and "updated_at" in result


def test_composition_unknown_dataset_404():
    from app.routers import datasets as datasets_router
    with pytest.raises(HTTPException) as exc_info:
        datasets_router.composition("nope-at-all")
    assert exc_info.value.status_code == 404


def test_composition_reports_read_only_for_fallback_ids(monkeypatch, tmp_path):
    from app.routers import datasets as DS
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    import duckdb
    from app.services.profiler import build_manifest
    df = pd.DataFrame({"fir_no": ["A1"]})
    con = duckdb.connect(); con.register("s", df)
    con.execute('CREATE TABLE "t" AS SELECT * FROM s')
    out = store.table_path("ksp-fir", "t"); out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY \"t\" TO '{out}' (FORMAT PARQUET)")
    m = build_manifest(con, ["t"], name="x", dataset_id="ksp-fir")  # legacy: no source stamp
    store.save_manifest(m)
    assert DS.composition("ksp-fir")["read_only"] is True
    m2 = _mk_upload(tmp_path, monkeypatch)
    assert DS.composition("d1")["read_only"] is False


# ---------------------------------------------------------------------------
# Router-level tests: intake `_run` dest routing
# ---------------------------------------------------------------------------

def test_intake_run_appends_into_dest_dataset(monkeypatch, tmp_path):
    import time

    import app.routers.intake as R
    _mk_upload(tmp_path, monkeypatch)  # dataset "d1" with table "cases" (3 rows)

    monkeypatch.setattr(
        R, "_llm_fn",
        lambda p: '[{"op":"dedupe_rows"}]' if "planner" in p else '{"done":true}'
    )
    df = pd.DataFrame({"fir_no": ["A4", "A5"], "crime_group": ["Cyber", "Cyber"]})
    job_id = R._start_job(df, key_col="fir_no", name="cases", dest_dataset_id="d1")
    for _ in range(80):
        if R.JOBS[job_id]["done"]:
            break
        time.sleep(0.05)
    job = R.JOBS[job_id]
    assert job["done"] and job["status"] == "complete"
    assert job["appended_to"] == "d1"
    assert job["added"] == 2 and job["duplicates_skipped"] == 0
    m = store.load_manifest("d1")
    assert m.table("cases").row_count == 5


def test_intake_run_falls_back_when_dest_is_readonly(monkeypatch, tmp_path):
    import time

    import app.routers.intake as R
    m = _mk_upload(tmp_path, monkeypatch)
    m.source = "seed"
    store.save_manifest(m)

    monkeypatch.setattr(
        R, "_llm_fn",
        lambda p: '[{"op":"dedupe_rows"}]' if "planner" in p else '{"done":true}'
    )
    df = pd.DataFrame({"fir_no": ["B1", "B2"], "crime_group": ["Cyber", "Cyber"]})
    job_id = R._start_job(df, key_col="fir_no", name="cases", dest_dataset_id="d1")
    for _ in range(80):
        if R.JOBS[job_id]["done"]:
            break
        time.sleep(0.05)
    job = R.JOBS[job_id]
    assert job["done"] and job["status"] == "complete"
    assert "note" in job and "d1" in job["note"]
    assert job["output_dataset_id"] is not None and job["output_dataset_id"] != "d1"
    assert "appended_to" not in job
