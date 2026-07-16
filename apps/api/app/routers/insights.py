"""Insights ("Command Brief") endpoints: a LLM-free findings bundle that paints
instantly, plus a separate compact LLM narrative that degrades to a deterministic
fallback. Network findings reuse the *cached* graph summary only (like the
handbook) so a request never blocks on a cold multi-second graph build."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.core import rescache, store
from app.routers import graph as graph_router
from app.services import insights as svc
from app.services import llm

router = APIRouter()


def _network_summary(dataset_id: str):
    """An already-available graph summary only — never a cold build. Two cheap
    sources: the in-process cache (populated when /graph/{id}/summary ran for a
    non-baked dataset), or a baked summary.json that seed/demo datasets ship —
    which bypasses that cache (see graph.summary), so check the file too.

    Matches the EXACT current dataset version — a stale prefix match would
    serve a pre-append graph summary and bake it into freshly-cached insights."""
    manifest = store.load_manifest(dataset_id)
    key = f"{dataset_id}@{rescache.dataset_version(manifest)}"
    summ = graph_router._summary_cache.get(key)
    if summ is not None:
        return summ
    baked = store.DATA_DIR / dataset_id / "summary.json"
    if baked.exists():
        return json.loads(baked.read_text())
    return None


def _network_summary_available(dataset_id: str) -> bool:
    """Cheap existence probe for the `net` cache-key param — avoids parsing the
    (potentially large) baked summary.json on every request just to know
    whether network data exists at all."""
    manifest = store.load_manifest(dataset_id)
    key = f"{dataset_id}@{rescache.dataset_version(manifest)}"
    if key in graph_router._summary_cache:
        return True
    return (store.DATA_DIR / dataset_id / "summary.json").exists()


@router.get("/{dataset_id}")
def get_insights(dataset_id: str, language: str = "en", refresh: bool = False) -> dict:
    # NOTE: findings are returned untranslated. build_insights is already CPU-heavy
    # (anomaly detection, risk, graph) and synchronously translating the findings too
    # exceeds AppSail's ~30s request budget (408). The Kannada Commander's Brief
    # (/brief?language=kn, a separate lightweight call) conveys the synthesis instead.
    def compute():
        return svc.build_insights(dataset_id, network_summary=_network_summary(dataset_id))
    try:
        # network availability is part of the key: a bundle computed before the
        # graph warmed gets upgraded (recomputed) once the summary exists.
        params = {"net": _network_summary_available(dataset_id)}
        return rescache.get_or_compute(dataset_id, "insights", params, compute, refresh)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")


def _llm_fn(messages):
    return llm.chat(messages).get("content") or ""


@router.get("/{dataset_id}/brief")
def get_brief(dataset_id: str, language: str = "en", refresh: bool = False) -> dict:
    def compute():
        ins = svc.build_insights(dataset_id, network_summary=_network_summary(dataset_id))
        return svc.commander_brief(ins, language=language, llm_fn=_llm_fn)
    try:
        params = {"language": language, "net": _network_summary_available(dataset_id)}
        return rescache.get_or_compute(dataset_id, "brief", params, compute, refresh,
                                       cache_if=lambda p: p.get("source") == "llm")
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
