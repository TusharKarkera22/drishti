from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import alerts as svc

router = APIRouter()


@router.get("/{dataset_id}")
def alerts(dataset_id: str, limit: int = 100) -> list[dict]:
    return svc.list_alerts(dataset_id, limit=limit)


@router.post("/{dataset_id}/scan")
def scan(dataset_id: str) -> dict:
    """Force a sentinel scan now (also the hook for a Catalyst Cron job)."""
    try:
        new = svc.scan_dataset(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    return {"created": len(new), "alerts": new}


@router.post("/{dataset_id}/{alert_id}/read")
def read(dataset_id: str, alert_id: str) -> dict:
    return {"ok": svc.mark_read(dataset_id, alert_id)}
