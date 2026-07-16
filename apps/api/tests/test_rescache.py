import json

import pandas as pd

from app.core import rescache, store
from app.models.manifest import ColumnSpec, DatasetManifest, TableSpec
from app.models.manifest import SemanticRole as SR


def _seed_manifest(tmp_path, ds="ds1", created="2026-01-01T00:00:00", updated=None):
    d = tmp_path / ds
    d.mkdir(parents=True, exist_ok=True)
    m = DatasetManifest(id=ds, name="x", created_at=created, updated_at=updated,
                        tables=[TableSpec(name="t")])
    (d / "manifest.json").write_text(m.model_dump_json())
    return m


def test_miss_computes_then_hit_serves_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_manifest(tmp_path)
    calls = {"n": 0}
    def compute():
        calls["n"] += 1
        return {"value": 42}
    r1 = rescache.get_or_compute("ds1", "insights", {}, compute)
    r2 = rescache.get_or_compute("ds1", "insights", {}, compute)
    assert calls["n"] == 1
    assert r1["value"] == r2["value"] == 42
    assert r1["cached"] is False and r2["cached"] is True
    assert r2["computed_at"] == r1["computed_at"]


def test_version_bump_recomputes(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_manifest(tmp_path)
    calls = {"n": 0}
    def compute():
        calls["n"] += 1
        return {"v": calls["n"]}
    rescache.get_or_compute("ds1", "risk", {}, compute)
    _seed_manifest(tmp_path, updated="2026-02-02T00:00:00")  # append bumped the version
    r = rescache.get_or_compute("ds1", "risk", {}, compute)
    assert calls["n"] == 2 and r["v"] == 2


def test_refresh_forces_and_params_key(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_manifest(tmp_path)
    calls = {"n": 0}
    def compute():
        calls["n"] += 1
        return {"v": calls["n"]}
    rescache.get_or_compute("ds1", "hotspots", {"cat": "Theft"}, compute)
    rescache.get_or_compute("ds1", "hotspots", {"cat": "Assault"}, compute)  # different key
    assert calls["n"] == 2
    rescache.get_or_compute("ds1", "hotspots", {"cat": "Theft"}, compute, refresh=True)
    assert calls["n"] == 3


def test_errors_are_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_manifest(tmp_path)
    calls = {"n": 0}
    def boom():
        calls["n"] += 1
        raise ValueError("nope")
    import pytest
    with pytest.raises(ValueError):
        rescache.get_or_compute("ds1", "x", {}, boom)
    with pytest.raises(ValueError):
        rescache.get_or_compute("ds1", "x", {}, boom)
    assert calls["n"] == 2  # second call recomputed — the failure was not cached


def test_clear_removes_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_manifest(tmp_path)
    calls = {"n": 0}
    def compute():
        calls["n"] += 1
        return {}
    rescache.get_or_compute("ds1", "a", {}, compute)
    rescache.clear("ds1")
    assert not (tmp_path / "ds1" / "cache").exists()  # clear() actually removed the cache dir
    rescache.get_or_compute("ds1", "a", {}, compute)
    assert calls["n"] == 2  # recompute recreated it


# ---------------------------------------------------------------------------
# Router-level wiring: endpoints must route through rescache.get_or_compute
# (real parquet + manifest, seeded the same way as test_view_resolution.py).
# ---------------------------------------------------------------------------

def _seed_crime_manifest(tmp_path, ds="ds_risk"):
    """A primary table with TIMESTAMP + ADMIN_AREA_1 roles — the minimum
    analytics.risk._ctx needs to accept the request without a 400."""
    d = tmp_path / ds
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=30, freq="D"),
        "area": ["North", "South"] * 15,
    })
    df.to_parquet(d / "events.parquet")
    manifest = DatasetManifest(id=ds, name=ds, tables=[
        TableSpec(name="events", is_primary=True, row_count=30, columns=[
            ColumnSpec(name="ts", dtype="timestamp", semantic_role=SR.TIMESTAMP),
            ColumnSpec(name="area", dtype="string", semantic_role=SR.ADMIN_AREA_1),
        ]),
    ])
    (d / "manifest.json").write_text(manifest.model_dump_json())
    return manifest


def test_analytics_risk_router_uses_rescache(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_crime_manifest(tmp_path)
    from app.routers import analytics as analytics_router
    from app.services import analytics as analytics_svc

    calls = {"n": 0}
    def fake_area_risk(*a, **kw):
        calls["n"] += 1
        return {"areas": [], "call": calls["n"]}
    monkeypatch.setattr(analytics_svc, "area_risk", fake_area_risk)

    r1 = analytics_router.risk("ds_risk")
    r2 = analytics_router.risk("ds_risk")
    assert calls["n"] == 1  # second call served from cache
    assert r1["call"] == r2["call"] == 1
    assert r2["cached"] is True and r1["cached"] is False
    assert "computed_at" in r1 and "computed_at" in r2

    r3 = analytics_router.risk("ds_risk", refresh=True)
    assert calls["n"] == 2
    assert r3["cached"] is False and r3["call"] == 2


def test_insights_router_uses_rescache(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_crime_manifest(tmp_path, ds="ds_ins")
    from app.routers import insights as insights_router
    from app.services import insights as insights_svc

    calls = {"n": 0}
    def fake_build_insights(*a, **kw):
        calls["n"] += 1
        return {"findings": [], "call": calls["n"]}
    monkeypatch.setattr(insights_svc, "build_insights", fake_build_insights)

    r1 = insights_router.get_insights("ds_ins")
    r2 = insights_router.get_insights("ds_ins")
    assert calls["n"] == 1
    assert r1["call"] == r2["call"] == 1
    assert r2["cached"] is True and r1["cached"] is False

    r3 = insights_router.get_insights("ds_ins", refresh=True)
    assert calls["n"] == 2
    assert r3["cached"] is False and r3["call"] == 2


def test_cache_if_skips_persisting_degraded_payloads(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _seed_manifest(tmp_path)
    calls = {"n": 0}
    def compute():
        calls["n"] += 1
        return {"source": "fallback" if calls["n"] == 1 else "llm", "brief": "x"}
    ok = lambda p: p.get("source") == "llm"
    r1 = rescache.get_or_compute("ds1", "brief", {}, compute, cache_if=ok)
    assert r1["source"] == "fallback" and r1["cached"] is False
    r2 = rescache.get_or_compute("ds1", "brief", {}, compute, cache_if=ok)  # retried, not pinned
    assert r2["source"] == "llm" and calls["n"] == 2
    r3 = rescache.get_or_compute("ds1", "brief", {}, compute, cache_if=ok)  # now cached
    assert r3["cached"] is True and calls["n"] == 2
