from __future__ import annotations

import json
import pickle
import threading

import networkx as nx
from fastapi import APIRouter, HTTPException

from app.core import store
from app.services import graph as svc

router = APIRouter()

# Graphs (and their summaries) are expensive to build over 200k rows;
# cache per dataset in-process.
_cache: dict[str, nx.Graph] = {}
_summary_cache: dict[str, dict] = {}
_build_lock = threading.Lock()  # serialize the expensive build across threads (pre-warm + requests)


def _cache_key(dataset_id: str, manifest) -> str:
    return f"{dataset_id}@{manifest.updated_at or manifest.created_at}"


def _graph(dataset_id: str) -> tuple[nx.Graph, object]:
    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    if not manifest.entities:
        raise HTTPException(400, "dataset has no linkable entities (no person-like tables found)")
    cache_key = _cache_key(dataset_id, manifest)
    if cache_key not in _cache:
        with _build_lock:
            if cache_key not in _cache:  # re-check: another thread may have built it while we waited
                _cache.clear()  # keep at most one graph in memory
                _summary_cache.clear()
                _cache[cache_key] = _load_or_build(dataset_id, manifest)
    return _cache[cache_key], manifest


def _load_or_build(dataset_id: str, manifest) -> nx.Graph:
    """Load a graph baked into the image (graph.pkl, ~0.2s) when present — else build it
    from the dataset (~7s+). Baking keeps cold-start under AppSail's request timeout;
    live-uploaded datasets have no baked graph and fall back to building."""
    pkl = store.DATA_DIR / dataset_id / "graph.pkl"
    if pkl.exists():
        with pkl.open("rb") as f:
            return pickle.load(f)
    return svc.build_graph(dataset_id, manifest)


@router.get("/{dataset_id}/summary")
def summary(dataset_id: str) -> dict:
    # A baked summary.json (Louvain etc. precomputed offline, ~10s) avoids a cold-start
    # community-detection pass — and doesn't even need the graph loaded.
    baked = store.DATA_DIR / dataset_id / "summary.json"
    if baked.exists():
        return json.loads(baked.read_text())
    g, manifest = _graph(dataset_id)
    key = _cache_key(dataset_id, manifest)
    if key not in _summary_cache:
        _summary_cache[key] = svc.graph_summary(g, manifest)
    return _summary_cache[key]


@router.get("/{dataset_id}/ego/{node_id:path}")
def ego(dataset_id: str, node_id: str, hops: int = 2) -> dict:
    g, _ = _graph(dataset_id)
    return svc.ego_network(g, node_id, hops=hops)


@router.get("/{dataset_id}/offender/{node_id:path}")
def offender(dataset_id: str, node_id: str) -> dict:
    """Return the MO profile for a repeat-offender graph node.

    Resolves the node's linked cases, districts, dominant crime subtype,
    and peak time-of-day band.  Never raises — missing/unknown node returns
    the zero-filled shape with case_count=0.
    """
    g, manifest = _graph(dataset_id)
    return svc.offender_profile(g, dataset_id, manifest, node_id)


@router.get("/{dataset_id}/search")
def search(dataset_id: str, q: str) -> list[dict]:
    g, _ = _graph(dataset_id)
    return svc.find_node(g, q)
