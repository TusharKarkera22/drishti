"""Predictive Case Triage endpoint: LOADS baked joblib model bundles (never
trains on the request path — training happens offline in
scripts/train_models.py) and scores the dataset's OPEN cases.

Degrades gracefully: 404 only when the dataset itself doesn't exist;
{"available": False, "reason": ...} (HTTP 200) when the dataset exists but has
no baked model (e.g. never trained, or train_detection() judged it ineligible)."""
from __future__ import annotations

import joblib
from fastapi import APIRouter, HTTPException

from app.core import rescache, store
from app.services import ml as svc

router = APIRouter()


def _load_bundle(dataset_id: str, name: str) -> dict | None:
    path = store.dataset_dir(dataset_id) / "models" / f"{name}.joblib"
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


@router.get("/{dataset_id}/predict")
def predict(dataset_id: str, limit: int = 25, refresh: bool = False) -> dict:
    try:
        store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")

    det_bundle = _load_bundle(dataset_id, "detection")
    if det_bundle is None:
        return {"available": False,
                "reason": "no baked detection model for this dataset "
                          "(run scripts/train_models.py)"}
    dur_bundle = _load_bundle(dataset_id, "duration")  # optional — None is fine

    def compute():
        try:
            return svc.predict_open(dataset_id, det_bundle, dur_bundle, limit=limit)
        except Exception as e:
            return {"available": False, "reason": f"prediction failed: {e}"}
    params = {"limit": limit}
    return rescache.get_or_compute(
        dataset_id, "predict", params, compute, refresh,
        cache_if=lambda p: p.get("available") is not False,
    )
