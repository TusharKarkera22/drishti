"""Append uploaded data into an existing ("living") dataset.

Monthly Excel/CSV drops land here instead of creating a brand-new dataset:
incoming tables are matched against the manifest (by name, then by column-set
similarity), aligned to the stored schema, deduped, and merged into the
parquet on disk. The manifest is refreshed (fresh row counts/stats) without
flipping any column's previously-assigned semantic role, the dataset version
is bumped (which auto-invalidates `rescache`), and the whole operation is
logged to a per-dataset JSONL audit trail.

Seed demo datasets (`manifest.source == "seed"`, or a handful of legacy seed
ids that predate the `source` field) are read-only and always raise
`ReadOnlyDatasetError`.
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import re
import threading

import duckdb
import pandas as pd

from app.core import rescache, store
from app.models.manifest import DatasetManifest, Relation, SemanticRole, TableSpec
from app.services import profiler

# Legacy seed datasets that predate the manifest `source` field — treated as
# read-only regardless of what `source` says (old manifests default to "upload").
SEED_FALLBACK_IDS = {"ksp-crime", "ksp-fir", "3af474fa5596"}

MATCH_JACCARD_THRESHOLD = 0.8

# Serializes append_tables() so a drop-zone append and an intake-thread append
# targeting the same dataset can never interleave their read-modify-write of
# the manifest/parquet on disk.
_APPEND_LOCK = threading.Lock()


class ReadOnlyDatasetError(Exception):
    """Raised when an append is attempted against a seed/demo dataset."""


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _log_path(dataset_id: str):
    return store.dataset_dir(dataset_id) / "ingest_log.jsonl"


def log_event(dataset_id: str, action: str, files: list[str], tables: list[dict]) -> None:
    """Append one JSON-line event to the dataset's ingest log."""
    record = {
        "at": _now_iso(),
        "action": action,
        "files": files,
        "tables": tables,
    }
    with _log_path(dataset_id).open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def read_log(dataset_id: str) -> list[dict]:
    """Read the dataset's ingest log, newest event first."""
    p = _log_path(dataset_id)
    if not p.exists():
        return []
    events = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    events.reverse()
    return events


def is_read_only(dataset_id: str, manifest: DatasetManifest) -> bool:
    """Seed/demo datasets are read-only (source stamp OR legacy fallback ids)."""
    return manifest.source == "seed" or dataset_id in SEED_FALLBACK_IDS


def _guard_writable(manifest: DatasetManifest) -> None:
    if is_read_only(manifest.id, manifest):
        raise ReadOnlyDatasetError(
            f"Dataset '{manifest.id}' is a read-only seed/demo dataset and cannot be appended to."
        )


def _match_table(name: str, df: pd.DataFrame, existing: list[TableSpec]) -> TableSpec | None:
    """Exact name match wins; otherwise the existing table whose normalized
    column-set has the highest Jaccard similarity with the incoming frame's
    column-set, provided it clears the threshold."""
    by_name = {t.name: t for t in existing}
    if name in by_name:
        return by_name[name]

    incoming_cols = {_normalize(c) for c in df.columns}
    best: tuple[float, TableSpec | None] = (0.0, None)
    for t in existing:
        existing_cols = {_normalize(c.name) for c in t.columns}
        if not existing_cols or not incoming_cols:
            continue
        inter = len(incoming_cols & existing_cols)
        union = len(incoming_cols | existing_cols)
        jaccard = inter / union if union else 0.0
        if jaccard > best[0]:
            best = (jaccard, t)
    if best[0] >= MATCH_JACCARD_THRESHOLD:
        return best[1]
    return None


def _align_columns(df: pd.DataFrame, table: TableSpec) -> tuple[pd.DataFrame, int]:
    """Reindex `df` onto `table`'s stored column order/set.
    Missing columns become pandas.NA; columns not present in `table` are
    dropped and counted."""
    existing_names = [c.name for c in table.columns]
    extras = [c for c in df.columns if c not in existing_names]
    aligned = df.reindex(columns=existing_names)
    return aligned, len(extras)


def _dedupe_against_stored(aligned: pd.DataFrame, stored: pd.DataFrame, table: TableSpec) -> tuple[pd.DataFrame, int]:
    """Drop incoming rows that already exist in `stored`. If the table has an
    ID-role column present in the incoming frame, dedupe by that id; otherwise
    dedupe by exact row match across all columns."""
    id_cols = [c.name for c in table.columns if c.semantic_role == SemanticRole.ID]
    id_col = next((c for c in id_cols if c in aligned.columns), None)

    if id_col is not None:
        existing_ids = set(stored[id_col].dropna()) if id_col in stored.columns else set()
        is_dup = aligned[id_col].isin(existing_ids)
        kept = aligned.loc[~is_dup]
        return kept, int(is_dup.sum())

    # Row-hash dedupe: drop incoming rows that are exact duplicates of a
    # stored row (compare on the shared/aligned column set).
    cols = list(aligned.columns)
    merged = aligned.merge(
        stored[cols].drop_duplicates(), on=cols, how="left", indicator=True
    )
    is_dup = merged["_merge"] == "both"
    kept = aligned.loc[~is_dup.to_numpy()]
    return kept, int(is_dup.sum())


def _profile_via_view(df: pd.DataFrame, table_name: str) -> TableSpec:
    con = duckdb.connect()
    try:
        con.register("v", df)
        con.execute(f'CREATE VIEW "{table_name}" AS SELECT * FROM v')
        return profiler.profile_table(con, table_name)
    finally:
        con.close()


def _preserve_roles(old: TableSpec, fresh: TableSpec) -> None:
    """Copy OLD semantic_role/label/role_confidence onto every column that
    already existed; columns new to this append keep the freshly-inferred role."""
    old_by_name = {c.name: c for c in old.columns}
    for col in fresh.columns:
        prev = old_by_name.get(col.name)
        if prev is not None:
            col.semantic_role = prev.semantic_role
            col.label = prev.label
            col.role_confidence = prev.role_confidence


def _link_new_table(new_spec: TableSpec, existing: list[TableSpec]) -> list[Relation]:
    """Detect FK relations between the new table and already-existing tables
    WITHOUT mutating the existing tables' stored semantic roles. Existing
    specs are deep-copied for the detection pass; only the new table's own
    spec is allowed to have its columns' roles updated (e.g. id -> foreign_key)."""
    relations: list[Relation] = []
    for t in existing:
        t_copy = copy.deepcopy(t)
        pair = [new_spec, t_copy]
        found = profiler.detect_relations(pair)
        for r in found:
            if r.from_table == new_spec.name or r.to_table == new_spec.name:
                relations.append(r)
        # Roles mutated by detect_relations on `new_spec` (the object we were
        # passed, not a copy) should stick; `t_copy`'s mutations are discarded.
    return relations


def append_tables(
    dataset_id: str,
    tables: dict[str, pd.DataFrame],
    *,
    files: list[str],
    action: str = "append",
) -> dict:
    with _APPEND_LOCK:
        manifest = store.load_manifest(dataset_id)
        _guard_writable(manifest)

        results: list[dict] = []

        for name, incoming in tables.items():
            matched = _match_table(name, incoming, manifest.tables)

            if matched is None:
                # ---- New table ---------------------------------------------
                out_path = store.table_path(dataset_id, name)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = out_path.with_suffix(".parquet.tmp")
                incoming.to_parquet(tmp_path, index=False)
                os.replace(tmp_path, out_path)

                new_spec = _profile_via_view(incoming, name)
                relations = _link_new_table(new_spec, manifest.tables)

                manifest.tables.append(new_spec)
                manifest.relations.extend(relations)
                manifest.entities.extend(profiler.detect_entities([new_spec]))

                results.append({
                    "name": name,
                    "added": new_spec.row_count,
                    "duplicates_skipped": 0,
                    "extras_ignored": 0,
                    "new_table": True,
                })
                continue

            # ---- Existing table: align, dedupe, append --------------------
            aligned, extras_ignored = _align_columns(incoming, matched)

            stored_path = store.table_path(dataset_id, matched.name)
            stored = pd.read_parquet(stored_path)

            kept, duplicates_skipped = _dedupe_against_stored(aligned, stored, matched)

            combined = pd.concat([stored, kept], ignore_index=True)
            tmp_path = stored_path.with_suffix(".parquet.tmp")
            combined.to_parquet(tmp_path, index=False)
            os.replace(tmp_path, stored_path)

            fresh_spec = _profile_via_view(combined, matched.name)
            _preserve_roles(matched, fresh_spec)

            # Replace the stored TableSpec in-place with the refreshed one. Look
            # up by identity (not `==`/list.index) since pydantic BaseModel
            # equality is structural — two same-shaped tables could otherwise
            # collide.
            idx = next(i for i, t in enumerate(manifest.tables) if t is matched)
            manifest.tables[idx] = fresh_spec

            results.append({
                "name": matched.name,
                "added": int(len(kept)),
                "duplicates_skipped": duplicates_skipped,
                "extras_ignored": extras_ignored,
                "new_table": False,
            })

        manifest.updated_at = _now_iso()
        rescache.clear(dataset_id)
        store.save_manifest(manifest)
        log_event(dataset_id, action, files, results)

        return {"tables": results, "dataset_version": manifest.updated_at}
