"""Versioned result cache for heavy analytics endpoints.

A result is valid for one *data version* of a dataset (manifest.updated_at or
created_at). Appending data bumps the version, so every cached result
auto-invalidates; until then, repeat visits are served in milliseconds instead
of recomputing multi-second analytics. Disk-persisted per dataset
({dataset}/cache/{name}-{hash}.json) with an in-process fast path.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
from typing import Any, Callable

from app.core import store

_MEM: dict[tuple, dict] = {}  # (dataset_id, key, version) -> payload


def dataset_version(manifest) -> str:
    return manifest.updated_at or manifest.created_at


def _key(name: str, params: dict) -> str:
    canon = json.dumps(params or {}, sort_keys=True, default=str)
    return f"{name}-{hashlib.md5(canon.encode()).hexdigest()[:12]}"


def _cache_dir(dataset_id: str):
    return store.dataset_dir(dataset_id) / "cache"


def get_or_compute(dataset_id: str, name: str, params: dict,
                   compute: Callable[[], dict], refresh: bool = False,
                   *, cache_if: Callable[[dict], bool] | None = None) -> dict:
    manifest = store.load_manifest(dataset_id)  # FileNotFoundError -> router 404
    version = dataset_version(manifest)
    key = _key(name, params)

    if not refresh:
        mem = _MEM.get((dataset_id, key, version))
        if mem is not None:
            return {**mem, "cached": True}
        f = _cache_dir(dataset_id) / f"{key}.json"
        if f.exists():
            try:
                rec = json.loads(f.read_text())
                if rec.get("version") == version:
                    payload = {**rec["payload"], "computed_at": rec["computed_at"]}
                    _MEM[(dataset_id, key, version)] = payload
                    return {**payload, "cached": True}
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # corrupt cache entry -> recompute

    payload: dict[str, Any] = compute()  # exceptions propagate uncached
    computed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {**payload, "computed_at": computed_at}

    # If cache_if predicate is provided and returns False, skip persistence
    if cache_if is not None and not cache_if(payload):
        return {**payload, "cached": False}

    _MEM[(dataset_id, key, version)] = payload
    d = _cache_dir(dataset_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(
        json.dumps({"version": version, "computed_at": computed_at, "payload": payload},
                   default=str))
    return {**payload, "cached": False}


def clear(dataset_id: str) -> None:
    shutil.rmtree(_cache_dir(dataset_id), ignore_errors=True)
    for k in [k for k in _MEM if k[0] == dataset_id]:
        _MEM.pop(k, None)
