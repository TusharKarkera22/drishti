"""Upload any CSV/Excel files → profile → semantic typing → manifest.

Multiple files in one upload become tables of the same dataset, which is
how cross-table relations (FIR → accused) are detected.
"""

from __future__ import annotations

import io
import re
import uuid

import duckdb
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core import store
from app.services import append, crime_pack
from app.services.profiler import build_manifest

router = APIRouter()


def _safe_table_name(filename: str) -> str:
    base = filename.rsplit(".", 1)[0].lower()
    return re.sub(r"[^a-z0-9_]+", "_", base).strip("_") or "table"


@router.post("")
async def ingest_files(
    files: list[UploadFile] = File(...),
    name: str = Form("Uploaded Dataset"),
) -> dict:
    dataset_id = uuid.uuid4().hex[:12]
    con = duckdb.connect()
    tables: list[str] = []

    for f in files:
        raw = await f.read()
        if f.filename and f.filename.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            df = pd.read_csv(io.BytesIO(raw))
        df.columns = [re.sub(r"[^a-zA-Z0-9_]+", "_", str(c)).strip("_").lower() for c in df.columns]
        table = _safe_table_name(f.filename or f"table_{len(tables)}")
        con.register("staging_df", df)
        # CTAS lets DuckDB re-infer better types (dates, ints) than pandas object cols
        con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM staging_df')
        con.unregister("staging_df")
        tables.append(table)

    for table in tables:
        out = store.table_path(dataset_id, table)
        out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY \"{table}\" TO '{out}' (FORMAT PARQUET)")

    manifest = build_manifest(con, tables, name=name, dataset_id=dataset_id)
    crime_pack.apply_if_match(manifest)
    manifest.source = "upload"
    store.save_manifest(manifest)
    append.log_event(
        dataset_id,
        "ingest",
        [f.filename for f in files],
        [
            {
                "name": t,
                "added": manifest.table(t).row_count,
                "duplicates_skipped": 0,
                "new_table": True,
            }
            for t in tables
        ],
    )
    return manifest.model_dump(mode="json")


@router.post("/{dataset_id}/append")
async def append_to_dataset(dataset_id: str,
                            files: list[UploadFile] = File(...)) -> dict:
    try:
        store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    tables: dict = {}
    names: list[str] = []
    for f in files:
        raw = await f.read()
        try:
            if f.filename and f.filename.lower().endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(raw))
            else:
                df = pd.read_csv(io.BytesIO(raw))
        except Exception as e:
            raise HTTPException(400, f"could not parse '{f.filename}': {e}")
        df.columns = [re.sub(r"[^a-zA-Z0-9_]+", "_", str(c)).strip("_").lower() for c in df.columns]
        tables[_safe_table_name(f.filename or f"table_{len(tables)}")] = df
        names.append(f.filename or "upload")
    try:
        return append.append_tables(dataset_id, tables, files=names)
    except append.ReadOnlyDatasetError:
        raise HTTPException(400, "This demo dataset is read-only — upload a copy from Home to extend it.")
