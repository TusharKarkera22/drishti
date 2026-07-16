import pandas as pd
import pytest

from app.core import store
from app.models.manifest import ColumnSpec, DatasetManifest, TableSpec
from app.models.manifest import SemanticRole as SR
from app.services import crime_pack


def _seed(tmp_path, dataset_id, tables: dict, manifest: DatasetManifest):
    d = tmp_path / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(d / f"{name}.parquet")
    (d / "manifest.json").write_text(manifest.model_dump_json())


def test_view_sql_field_roundtrips():
    t = TableSpec(name="v", view_sql="SELECT 1 AS x")
    assert TableSpec.model_validate_json(t.model_dump_json()).view_sql == "SELECT 1 AS x"


def test_connect_materializes_view_sql(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    base = pd.DataFrame({"GravityOffenceID": [1, 2], "n": [10, 20]})
    lk = pd.DataFrame({"GravityOffenceID": [1, 2], "LookupValue": ["Heinous", "Non-Heinous"]})
    mani = DatasetManifest(id="ds_v", name="v", tables=[
        TableSpec(name="CaseMaster"), TableSpec(name="GravityOffence"),
        TableSpec(name="case_view", is_primary=True, view_sql=(
            'SELECT c."n" AS n, g."LookupValue" AS gravity '
            'FROM "CaseMaster" c LEFT JOIN "GravityOffence" g '
            'ON g."GravityOffenceID" = c."GravityOffenceID"')),
    ])
    _seed(tmp_path, "ds_v", {"CaseMaster": base, "GravityOffence": lk}, mani)
    con = store.connect("ds_v")
    try:
        rows = con.execute('SELECT gravity FROM "case_view" ORDER BY n').fetchall()
    finally:
        con.close()
    assert [r[0] for r in rows] == ["Heinous", "Non-Heinous"]


def test_connect_without_view_sql_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    df = pd.DataFrame({"a": [1, 2, 3]})
    mani = DatasetManifest(id="ds_plain", name="p", tables=[TableSpec(name="t")])
    _seed(tmp_path, "ds_plain", {"t": df}, mani)
    con = store.connect("ds_plain")
    try:
        assert con.execute('SELECT count(*) FROM "t"').fetchone()[0] == 3
    finally:
        con.close()


def test_connect_missing_dataset_dir_is_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    con = store.connect("does_not_exist")  # no dir, no parquet, no manifest
    try:
        assert con.execute("SELECT 1").fetchone()[0] == 1
    finally:
        con.close()


def test_resolve_fk_labels_adds_label_and_view():
    import duckdb
    from app.services import profiler

    con = duckdb.connect()
    con.execute('CREATE TABLE "cases" AS SELECT * FROM (VALUES '
                "(1, 1), (2, 2), (3, 1)) AS t(case_id, grade_id)")
    con.execute('CREATE TABLE "grade" AS SELECT * FROM (VALUES '
                "(1, 'Open'), (2, 'Closed')) AS t(grade_id, grade_name)")
    mani = profiler.build_manifest(con, ["cases", "grade"], name="x", dataset_id="x")
    cases = mani.table("cases")
    derived = [c for c in cases.columns if c.name == "grade_name"]
    assert derived, "expected a resolved label column 'grade_name'"
    assert cases.view_sql and "LEFT JOIN" in cases.view_sql
    con.execute(f'CREATE VIEW "cases_v" AS {cases.view_sql}')
    vals = {r[0] for r in con.execute('SELECT grade_name FROM "cases_v"').fetchall()}
    assert vals == {"Open", "Closed"}


def _crime_manifest_with(cols):
    # prepend signal-bearing columns so looks_like_crime_data() (needs >=2 hits) fires
    cols = [("fir_no", SR.ID), ("accused_count", SR.MEASURE)] + cols
    return DatasetManifest(id="m", name="m", tables=[TableSpec(
        name="case_master_analytics", is_primary=True, row_count=100,
        columns=[ColumnSpec(name=n, dtype="string", semantic_role=r) for n, r in cols])])


def test_fir_kpis_added_when_gravity_present():
    m = _crime_manifest_with([("district", SR.ADMIN_AREA_1), ("gravity", SR.CATEGORY),
                              ("case_status", SR.STATUS), ("crime_major_head", SR.CATEGORY)])
    cs = next(c for c in m.tables[0].columns if c.name == "case_status")
    cs.stats.top_values = [{"value": "Under Investigation", "count": 9}]
    crime_pack.apply_if_match(m)
    ids = {k.id for k in m.kpis}
    assert "heinous_cases" in ids and "pending_cases" in ids


def test_fir_kpis_absent_for_plain_crime():
    # representative of real ksp-crime: populated status column but NO gravity column
    m = _crime_manifest_with([("district", SR.ADMIN_AREA_1), ("crime_group", SR.CATEGORY),
                              ("case_status", SR.STATUS)])
    cs = next(c for c in m.tables[0].columns if c.name == "case_status")
    cs.stats.top_values = [{"value": "Under Investigation", "count": 9}]
    crime_pack.apply_if_match(m)
    ids = {k.id for k in m.kpis}
    assert "heinous_cases" not in ids and "pending_cases" not in ids
