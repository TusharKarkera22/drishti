"""Statistical intelligence: hotspots, spike alerts, anomalies, risk scores.

All endpoints are manifest-driven — they look up which columns play the
timestamp/lat/lng/admin-area roles, so they work on any dataset that has
those roles, crime or not.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core import rescache, store
from app.models.manifest import SemanticRole
from app.services import analytics as svc

router = APIRouter()


def _ctx(dataset_id: str):
    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    t = manifest.primary_table()
    if not t:
        raise HTTPException(400, "dataset has no tables")
    return manifest, t


@router.get("/{dataset_id}/hotspots")
def hotspots(dataset_id: str, category: str | None = None, hour_from: int | None = None,
             hour_to: int | None = None, cell_km: float = 2.0, refresh: bool = False) -> dict:
    manifest, t = _ctx(dataset_id)
    lat = t.first_by_role(SemanticRole.LATITUDE)
    lng = t.first_by_role(SemanticRole.LONGITUDE)
    if not (lat and lng):
        raise HTTPException(400, "dataset has no geo columns")
    def compute():
        return svc.grid_hotspots(
            dataset_id, t, lat.name, lng.name,
            category=category, hour_from=hour_from, hour_to=hour_to, cell_km=cell_km,
        )
    params = {"category": category, "hf": hour_from, "ht": hour_to, "cell": cell_km}
    return rescache.get_or_compute(dataset_id, "hotspots", params, compute, refresh)


@router.get("/{dataset_id}/spikes")
def spikes(dataset_id: str, window_days: int = 28, z_threshold: float = 2.5,
          refresh: bool = False) -> dict:
    """Emerging-trend alerts: category × admin-area cells whose recent volume
    deviates from their own historical baseline (powers red-zone pulses)."""
    manifest, t = _ctx(dataset_id)
    time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
    if not time_col:
        raise HTTPException(400, "dataset has no time column")
    cat = t.first_by_role(SemanticRole.CATEGORY)
    area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
    def compute():
        return svc.spike_alerts(
            dataset_id, t, time_col.name,
            category_col=cat.name if cat else None,
            area_col=area.name if area else None,
            window_days=window_days, z_threshold=z_threshold,
        )
    params = {"z": z_threshold}
    return rescache.get_or_compute(dataset_id, "spikes", params, compute, refresh)


@router.get("/{dataset_id}/anomalies")
def anomalies(dataset_id: str, contamination: float = 0.01, limit: int = 50,
             refresh: bool = False) -> dict:
    manifest, t = _ctx(dataset_id)
    def compute():
        return svc.detect_anomalies(dataset_id, t, contamination=contamination, limit=limit)
    params = {"limit": limit}
    return rescache.get_or_compute(dataset_id, "anomalies", params, compute, refresh)


@router.get("/{dataset_id}/correlation")
def correlation(dataset_id: str, refresh: bool = False) -> dict:
    """Socio-economic correlation scatter: per-lakh crime rate vs demographic factors.
    Returns {available, correlations, n_areas, points} on success or
    {available: false, reason} when demographics are absent — never raises."""
    manifest, t = _ctx(dataset_id)
    area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
    if not area:
        return {"available": False, "reason": "no admin_area_1 column in primary table"}
    def compute():
        return svc.socioeconomic_correlation(dataset_id, manifest, area.name)
    return rescache.get_or_compute(dataset_id, "correlation", {}, compute, refresh)


@router.get("/{dataset_id}/risk")
def risk(dataset_id: str, horizon_days: int = 7, refresh: bool = False) -> dict:
    """Per-area risk score combining recent volume, trend slope, and spike state."""
    manifest, t = _ctx(dataset_id)
    time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
    area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
    if not (time_col and area):
        raise HTTPException(400, "risk scoring needs time and admin-area columns")
    def compute():
        demo = svc.load_demographics(dataset_id, manifest, area.name)
        return svc.area_risk(dataset_id, t, time_col.name, area.name,
                             horizon_days=horizon_days, demographics=demo)
    params = {"horizon_days": horizon_days}
    return rescache.get_or_compute(dataset_id, "risk", params, compute, refresh)
