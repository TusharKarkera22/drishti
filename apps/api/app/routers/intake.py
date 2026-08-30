"""Data Intake: upload raw messy CSV/XLSX -> background agentic cleaning job -> a cleaned
dataset that flows into the existing surfaces. Job status is polled for the live pipeline
view. The job runs on a daemon thread (cleaning is CPU-bound pandas; the AppSail container
is long-running). Jobs live in-process and die on container recycle (fine for the demo)."""
from __future__ import annotations

import re
import threading
import uuid

import duckdb
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core import store
from app.core.config import DATA_DIR
from app.routers.ingest import _safe_table_name, read_upload_dataframe
from app.services import append as append_svc
from app.services import crime_pack, intake
from app.services import llm
from app.services.profiler import build_manifest

router = APIRouter()

JOBS: dict[str, dict] = {}


def _llm_fn(prompt: str) -> str:
    return llm.chat([{"role": "user", "content": prompt}]).get("content", "")


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"[^a-zA-Z0-9_]+", "_", str(c)).strip("_").lower() for c in df.columns]
    return df


def _write_cleaned_dataset(df: pd.DataFrame, name: str) -> str:
    """Persist a cleaned frame as a new dataset (parquet + manifest) so every existing
    surface (Overview/Network/...) renders it. Reuses the ingest profiler."""
    dataset_id = uuid.uuid4().hex[:12]
    df = _norm_cols(df)
    con = duckdb.connect()
    con.register("staging_df", df)
    con.execute('CREATE TABLE "records" AS SELECT * FROM staging_df')
    con.unregister("staging_df")
    out = store.table_path(dataset_id, "records")
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY \"records\" TO '{out}' (FORMAT PARQUET)")
    manifest = build_manifest(con, ["records"], name=name, dataset_id=dataset_id)
    crime_pack.apply_if_match(manifest)
    store.save_manifest(manifest)
    return dataset_id


def _run(job_id: str, df: pd.DataFrame, key_col: str, name: str) -> None:
    job = JOBS[job_id]
    try:
        def progress(it: dict) -> None:
            job["iterations"].append(it)
            job["status"] = f"iteration {it['iteration']}"
        log = intake.run_intake(df, key_col=key_col, llm_fn=_llm_fn, max_iter=2, on_progress=progress)

        dest = job.get("dest_dataset_id") or ""
        if dest:
            try:
                table = _safe_table_name(name)
                res = append_svc.append_tables(
                    dest, {table: _norm_cols(log["cleaned_df"])},
                    files=[name], action="intake")
                t0 = res["tables"][0]
                job.update(appended_to=dest, added=t0["added"],
                           duplicates_skipped=t0["duplicates_skipped"])
                ds_id = dest
            except (append_svc.ReadOnlyDatasetError, FileNotFoundError) as e:
                job["note"] = f"could not append to {dest} ({e}); created a new dataset instead"
                ds_id = _write_cleaned_dataset(log["cleaned_df"], name)
        else:
            ds_id = _write_cleaned_dataset(log["cleaned_df"], name)

        job.update(status="complete", done=True, report=log["report"],
                   output_dataset_id=ds_id, quarantined=len(log["quarantined"]),
                   rows_in=len(df), rows_out=len(log["cleaned_df"]))
    except Exception as e:  # never leave a job hanging
        job.update(status="failed", done=True, error=str(e))


def _start_job(df: pd.DataFrame, *, key_col: str, name: str, job_id: str | None = None,
              dest_dataset_id: str = "") -> str:
    job_id = job_id or uuid.uuid4().hex[:10]
    JOBS[job_id] = {"job_id": job_id, "name": name, "status": "running", "done": False,
                    "iterations": [], "report": "", "output_dataset_id": None,
                    "dest_dataset_id": dest_dataset_id}
    threading.Thread(target=_run, args=(job_id, df, key_col, name), daemon=True).start()
    return job_id


@router.post("/clean")
async def clean(file: UploadFile = File(...), name: str = Form("Cleaned Dataset"),
                dest_dataset_id: str = Form("")) -> dict:
    raw, df = await read_upload_dataframe(file)
    fn = (file.filename or "upload.csv").lower()
    df = _norm_cols(df)
    key_col = df.columns[0]
    job_id = uuid.uuid4().hex[:10]
    # persist the original bytes (basis for reversibility); /srv/data is ephemeral but fine for a job
    raw_dir = DATA_DIR / "intake" / job_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    ext = fn.rsplit(".", 1)[1] if "." in fn else "csv"
    (raw_dir / f"raw.{ext}").write_bytes(raw)
    _start_job(df, key_col=key_col, name=name, job_id=job_id, dest_dataset_id=dest_dataset_id)
    return {"job_id": job_id, "key_col": key_col, "rows": int(len(df))}


@router.get("/clean/{job_id}/status")
def status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job
