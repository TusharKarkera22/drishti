"""Dataset storage: parquet files + manifest.json per dataset, queried via DuckDB.

Layout: {DATA_DIR}/{dataset_id}/{table}.parquet + manifest.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from app.core.config import DATA_DIR
from app.models.manifest import DatasetManifest

logger = logging.getLogger(__name__)


def dataset_dir(dataset_id: str) -> Path:
    d = DATA_DIR / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_datasets() -> list[DatasetManifest]:
    out = []
    if not DATA_DIR.exists():
        return out
    for d in sorted(DATA_DIR.iterdir()):
        mf = d / "manifest.json"
        if mf.exists():
            out.append(DatasetManifest.model_validate_json(mf.read_text()))
    return out


def load_manifest(dataset_id: str) -> DatasetManifest:
    mf = DATA_DIR / dataset_id / "manifest.json"
    if not mf.exists():
        raise FileNotFoundError(f"No manifest for dataset '{dataset_id}'")
    return DatasetManifest.model_validate_json(mf.read_text())


def save_manifest(manifest: DatasetManifest) -> None:
    d = dataset_dir(manifest.id)
    (d / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))


def table_path(dataset_id: str, table: str) -> Path:
    return DATA_DIR / dataset_id / f"{table}.parquet"


def connect(dataset_id: str) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with every parquet of the dataset registered as a view.
    Tables whose manifest TableSpec carries `view_sql` are then created as SQL
    views (FK->label resolution etc.), so every consumer sees resolved columns."""
    con = duckdb.connect()
    for pq in (DATA_DIR / dataset_id).glob("*.parquet"):
        con.execute(
            f"CREATE VIEW \"{pq.stem}\" AS SELECT * FROM read_parquet('{pq}')"
        )
    mf = DATA_DIR / dataset_id / "manifest.json"
    if mf.exists():
        try:
            manifest = DatasetManifest.model_validate_json(mf.read_text())
            for t in manifest.tables:
                if t.view_sql:
                    con.execute(f'CREATE OR REPLACE VIEW "{t.name}" AS {t.view_sql}')
        except Exception as e:
            logger.warning(
                "view_sql wiring failed for dataset %s: %s", dataset_id, e)
    return con
