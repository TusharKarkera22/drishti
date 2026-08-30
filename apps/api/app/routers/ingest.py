"""Upload any CSV/Excel files → profile → semantic typing → manifest.

Multiple files in one upload become tables of the same dataset, which is
how cross-table relations (FIR → accused) are detected.
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile

import duckdb
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core import store
from app.core.config import (
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_FILES,
    MAX_UPLOAD_ROWS,
    MAX_UPLOAD_TOTAL_BYTES,
    MAX_XLSX_COMPRESSION_RATIO,
    MAX_XLSX_MEMBER_BYTES,
    MAX_XLSX_MEMBERS,
    MAX_XLSX_UNCOMPRESSED_BYTES,
)
from app.services import append, crime_pack
from app.services.profiler import build_manifest

router = APIRouter()

_ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


def _safe_table_name(filename: str) -> str:
    base = filename.rsplit(".", 1)[0].lower()
    return re.sub(r"[^a-z0-9_]+", "_", base).strip("_") or "table"


def _extension(filename: str) -> str:
    name = (filename or "").lower()
    return f".{name.rsplit('.', 1)[1]}" if "." in name else ""


def _validate_upload_count(files: list[UploadFile]) -> None:
    if not files:
        raise HTTPException(400, "select at least one CSV or XLSX file")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            400,
            f"upload at most {MAX_UPLOAD_FILES} file"
            f"{'s' if MAX_UPLOAD_FILES != 1 else ''} at a time",
        )


def _validate_xlsx_archive(raw: bytes, filename: str) -> None:
    """Reject archive expansion attacks before openpyxl allocates workbook XML."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise HTTPException(400, f"could not parse '{filename}': invalid XLSX archive") from exc

    if len(members) > MAX_XLSX_MEMBERS:
        raise HTTPException(413, f"'{filename}' contains too many XLSX archive members")
    if any(member.flag_bits & 0x1 for member in members):
        raise HTTPException(400, f"'{filename}' contains encrypted XLSX content")

    expanded = sum(member.file_size for member in members)
    if expanded > MAX_XLSX_UNCOMPRESSED_BYTES:
        raise HTTPException(413, f"'{filename}' exceeds the XLSX expanded size limit")
    if any(member.file_size > MAX_XLSX_MEMBER_BYTES for member in members):
        raise HTTPException(413, f"'{filename}' contains an oversized XLSX archive member")

    compressed = sum(max(member.compress_size, 1) for member in members)
    if expanded and expanded / compressed > MAX_XLSX_COMPRESSION_RATIO:
        raise HTTPException(413, f"'{filename}' exceeds the XLSX compression ratio limit")


async def read_upload_dataframe(
    upload: UploadFile,
    *,
    max_rows: int | None = None,
    max_bytes: int | None = None,
) -> tuple[bytes, pd.DataFrame]:
    """Read and parse one upload within the public demo's hard limits."""
    filename = upload.filename or "upload"
    ext = _extension(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(415, "only CSV and XLSX uploads are supported")

    byte_limit = min(MAX_UPLOAD_BYTES, max_bytes) if max_bytes is not None else MAX_UPLOAD_BYTES
    raw = await upload.read(byte_limit + 1)
    if len(raw) > byte_limit:
        if max_bytes is not None and max_bytes < MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"combined uploads exceed the {MAX_UPLOAD_TOTAL_BYTES // (1024 * 1024)} MB request limit",
            )
        raise HTTPException(
            413,
            f"'{filename}' exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB per-file limit",
        )
    if not raw:
        raise HTTPException(400, f"'{filename}' is empty")

    row_limit = MAX_UPLOAD_ROWS if max_rows is None else max_rows
    try:
        if ext == ".xlsx":
            _validate_xlsx_archive(raw, filename)
            frame = pd.read_excel(io.BytesIO(raw), nrows=row_limit + 1)
        else:
            frame = pd.read_csv(io.BytesIO(raw), nrows=row_limit + 1)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"could not parse '{filename}': {exc}") from exc

    if len(frame) > row_limit:
        raise HTTPException(413, f"uploads may contain at most {MAX_UPLOAD_ROWS} rows total")
    if frame.empty:
        raise HTTPException(400, f"'{filename}' has no data rows")
    return raw, frame


@router.post("")
async def ingest_files(
    files: list[UploadFile] = File(...),
    name: str = Form("Uploaded Dataset"),
) -> dict:
    _validate_upload_count(files)
    dataset_id = uuid.uuid4().hex[:12]
    con = duckdb.connect()
    tables: list[str] = []
    frames: list[tuple[UploadFile, pd.DataFrame]] = []
    total_bytes = 0
    total_rows = 0

    for f in files:
        remaining_bytes = MAX_UPLOAD_TOTAL_BYTES - total_bytes
        raw, df = await read_upload_dataframe(
            f,
            max_rows=MAX_UPLOAD_ROWS - total_rows,
            max_bytes=remaining_bytes,
        )
        total_bytes += len(raw)
        total_rows += len(df)
        frames.append((f, df))

    for f, df in frames:
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
    _validate_upload_count(files)
    tables: dict = {}
    names: list[str] = []
    total_bytes = 0
    total_rows = 0
    for f in files:
        remaining_bytes = MAX_UPLOAD_TOTAL_BYTES - total_bytes
        raw, df = await read_upload_dataframe(
            f,
            max_rows=MAX_UPLOAD_ROWS - total_rows,
            max_bytes=remaining_bytes,
        )
        total_bytes += len(raw)
        total_rows += len(df)
        df.columns = [re.sub(r"[^a-zA-Z0-9_]+", "_", str(c)).strip("_").lower() for c in df.columns]
        tables[_safe_table_name(f.filename or f"table_{len(tables)}")] = df
        names.append(f.filename or "upload")
    try:
        return append.append_tables(dataset_id, tables, files=names)
    except append.ReadOnlyDatasetError:
        raise HTTPException(400, "This demo dataset is read-only — upload a copy from Home to extend it.")
