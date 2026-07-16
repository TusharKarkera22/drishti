"""Predictive-Intelligence layer — TDD tests.

Covers:
  Task 1 — build_features + train_detection (HistGradientBoostingClassifier)
  Task 2 — train_duration (HistGradientBoostingRegressor) + predict_open
  Task 3 — router + findings_from_predictions

Seed technique mirrors test_psgaps.py / test_view_resolution.py: write parquet +
manifest.json under a tmp_path, then monkeypatch store.DATA_DIR.

GOVERNANCE: none of the seeded feature tables below carry caste/religion/identity
columns as features — only case-level signals (crime type, gravity, area, time,
report delay, property loss, n_accused). See app/services/ml.py module docstring.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core import store
from app.models.manifest import (
    ColumnSpec,
    DatasetManifest,
    Relation,
    TableSpec,
)
from app.models.manifest import SemanticRole as SR


# ---------------------------------------------------------------------------
# Shared seed helper (mirrors test_psgaps._seed)
# ---------------------------------------------------------------------------

def _seed(tmp_path, dataset_id: str, tables: dict[str, pd.DataFrame],
          manifest: DatasetManifest):
    d = tmp_path / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(d / f"{name}.parquet")
    (d / "manifest.json").write_text(manifest.model_dump_json())


def _col(name: str, role: SR, dtype: str = "string") -> ColumnSpec:
    return ColumnSpec(name=name, dtype=dtype, semantic_role=role)


# ---------------------------------------------------------------------------
# Task 1 — build_features / train_detection dataset
# ---------------------------------------------------------------------------

_DETECTED_STATUSES = ["Chargesheeted", "Convicted", "Acquitted"]
_UNDETECTED_STATUSES = ["Closed - Undetected"]
_OPEN_STATUSES = ["Under Investigation"]


def _make_detection_dataset(tmp_path, dataset_id="ds_det", n=400, n_open=15):
    """n closed cases (mostly detected, some undetected) + n_open Under-Investigation
    cases. Crime type / area / timestamps vary so features are non-degenerate."""
    rng = np.random.default_rng(7)
    rows = []
    areas = ["AreaA", "AreaB", "AreaC"]
    cats = ["Theft", "Robbery", "Cybercrime"]
    base = pd.Timestamp("2024-01-01")
    for i in range(n):
        occurrence = base + pd.Timedelta(days=int(rng.integers(0, 500)),
                                          hours=int(rng.integers(0, 24)))
        reported = occurrence + pd.Timedelta(hours=int(rng.integers(0, 48)))
        # detected cases skew toward Cybercrime being *undetected* more often
        cat = cats[i % 3]
        if cat == "Cybercrime" and rng.random() < 0.5:
            status = rng.choice(_UNDETECTED_STATUSES)
        else:
            status = rng.choice(_DETECTED_STATUSES + _UNDETECTED_STATUSES,
                                 p=[0.5, 0.2, 0.1, 0.2])
        rows.append({
            "case_id": i,
            "fir_no": f"FIR{i}",
            "cat": cat,
            "area": areas[i % 3],
            "occurrence_ts": occurrence,
            "reported_ts": reported,
            "loss": float(rng.integers(0, 50000)),
            "status": status,
        })
    for j in range(n_open):
        i = n + j
        occurrence = base + pd.Timedelta(days=int(rng.integers(400, 500)))
        rows.append({
            "case_id": i,
            "fir_no": f"FIR{i}",
            "cat": cats[i % 3],
            "area": areas[i % 3],
            "occurrence_ts": occurrence,
            "reported_ts": occurrence + pd.Timedelta(hours=2),
            "loss": float(rng.integers(0, 50000)),
            "status": "Under Investigation",
        })
    df = pd.DataFrame(rows)
    manifest = DatasetManifest(id=dataset_id, name=dataset_id, tables=[
        TableSpec(name="events", is_primary=True, columns=[
            _col("case_id", SR.ID, "integer"),
            _col("fir_no", SR.ID),
            _col("cat", SR.CATEGORY),
            _col("area", SR.ADMIN_AREA_1),
            _col("occurrence_ts", SR.TIMESTAMP, "timestamp"),
            _col("reported_ts", SR.TIMESTAMP, "timestamp"),
            _col("loss", SR.MONEY, "float"),
            _col("status", SR.STATUS),
        ])
    ])
    _seed(tmp_path, dataset_id, {"events": df}, manifest)
    return manifest


def test_build_features_training_excludes_open_cases(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    manifest = _make_detection_dataset(tmp_path)
    from app.services.ml import build_features
    X, y, ids = build_features("ds_det", manifest, for_training=True)
    assert y is not None
    assert len(X) == len(y) == len(ids) == 400  # only closed cases
    assert set(np.unique(y.dropna())) <= {0, 1}


def test_build_features_scoring_returns_only_open_cases_with_no_y(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    manifest = _make_detection_dataset(tmp_path)
    from app.services.ml import build_features
    X, y, ids = build_features("ds_det", manifest, for_training=False)
    assert y is None
    assert len(X) == len(ids) == 15  # only Under-Investigation rows


def test_build_features_has_expected_case_level_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    manifest = _make_detection_dataset(tmp_path)
    from app.services.ml import build_features
    X, y, ids = build_features("ds_det", manifest, for_training=True)
    for col in ("crime_type", "area", "hour", "dow", "report_delay_h", "property_loss"):
        assert col in X.columns, f"missing feature column {col} in {list(X.columns)}"
    # governance: no identity/demographic columns ever appear as features
    for banned in ("caste", "religion", "gender", "name", "phone", "address"):
        assert not any(banned in c.lower() for c in X.columns), X.columns


def test_train_detection_available_with_enough_labelled_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_detection_dataset(tmp_path)
    from app.services.ml import train_detection
    res = train_detection("ds_det")
    assert res["available"] is True
    assert 0.0 <= res["base_rate"] <= 1.0
    assert "auc" in res and res["auc"] is not None
    assert res["importances"]  # non-empty dict
    assert res["n_train"] == 400
    assert res["model"] is not None
    assert res["features"]


def test_train_detection_unavailable_when_no_status_column(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    df = pd.DataFrame({"case_id": range(300), "cat": ["Theft"] * 300})
    manifest = DatasetManifest(id="ds_nostatus", name="x", tables=[
        TableSpec(name="events", is_primary=True, columns=[
            _col("case_id", SR.ID, "integer"), _col("cat", SR.CATEGORY),
        ])
    ])
    _seed(tmp_path, "ds_nostatus", {"events": df}, manifest)
    from app.services.ml import train_detection
    res = train_detection("ds_nostatus")
    assert res["available"] is False
    assert "reason" in res


def test_train_detection_unavailable_when_too_few_labelled_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_detection_dataset(tmp_path, dataset_id="ds_small", n=50, n_open=5)
    from app.services.ml import train_detection
    res = train_detection("ds_small")
    assert res["available"] is False
    assert "reason" in res


def test_label_helpers_classify_statuses_case_insensitively():
    from app.services.ml import _detected_labels, _undetected_labels
    assert _detected_labels("Chargesheeted") is True
    assert _detected_labels("CONVICTED") is True
    assert _detected_labels("Acquitted") is True
    assert _detected_labels("Charge Sheeted") is True  # ksp-fir spelling
    assert _detected_labels("Under Investigation") is False
    assert _undetected_labels("Closed - Undetected") is True
    assert _undetected_labels("Closed") is True  # ksp-fir spelling
    assert _undetected_labels("Chargesheeted") is False


# ---------------------------------------------------------------------------
# Task 2 — train_duration + predict_open
# ---------------------------------------------------------------------------

def _make_duration_dataset(tmp_path, dataset_id="ds_dur", n=300):
    """Same shape as the detection dataset, plus a ChargesheetDetails-like table
    with a csdate column joined via manifest.relations on case_id."""
    manifest = _make_detection_dataset(tmp_path, dataset_id=dataset_id, n=n, n_open=15)
    con_events = pd.read_parquet(tmp_path / dataset_id / "events.parquet")
    rng = np.random.default_rng(3)
    # only detected (chargesheeted/convicted/acquitted) cases get a chargesheet row
    detected = con_events[con_events["status"].isin(_DETECTED_STATUSES)]
    cs_rows = []
    for _, r in detected.iterrows():
        days = int(rng.integers(5, 120))
        cs_rows.append({
            "cs_id": len(cs_rows),
            "case_ref": r["case_id"],
            "csdate": r["occurrence_ts"] + pd.Timedelta(days=days),
        })
    cs_df = pd.DataFrame(cs_rows)
    manifest.tables.append(TableSpec(name="chargesheets", columns=[
        _col("cs_id", SR.ID, "integer"),
        _col("case_ref", SR.FOREIGN_KEY, "integer"),
        _col("csdate", SR.TIMESTAMP, "timestamp"),
    ]))
    manifest.relations.append(Relation(
        from_table="chargesheets", from_column="case_ref",
        to_table="events", to_column="case_id",
    ))
    d = tmp_path / dataset_id
    cs_df.to_parquet(d / "chargesheets.parquet")
    (d / "manifest.json").write_text(manifest.model_dump_json())
    return manifest


def test_train_duration_available_when_resolution_date_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_duration_dataset(tmp_path)
    from app.services.ml import train_duration
    res = train_duration("ds_dur")
    assert res["available"] is True
    assert res["mae"] is not None and res["mae"] >= 0
    assert res["median_days"] is not None
    assert res["p90_days"] is not None
    assert res["model"] is not None
    assert res["features"]


def test_train_duration_unavailable_without_resolution_date(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_detection_dataset(tmp_path)  # no chargesheets table -> like ksp-crime
    from app.services.ml import train_duration
    res = train_duration("ds_det")
    assert res["available"] is False
    assert "reason" in res


def test_predict_open_scores_open_cases_with_factors_and_by_area(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    manifest = _make_duration_dataset(tmp_path)
    from app.services.ml import predict_open, train_detection, train_duration
    det = train_detection("ds_dur")
    dur = train_duration("ds_dur")
    res = predict_open("ds_dur", det, dur, limit=25)
    assert res["available"] is True
    assert len(res["flagged"]) > 0
    for f in res["flagged"]:
        assert 0.0 <= f["detection_prob"] <= 1.0
        assert f["factors"]  # non-empty lightweight explanation
        assert "id" in f
        assert "stall" in f
    # sorted ascending by detection_prob (worst first)
    probs = [f["detection_prob"] for f in res["flagged"]]
    assert probs == sorted(probs)
    assert res["by_area"]
    for a in res["by_area"]:
        assert "area" in a and "predicted_detection_rate" in a and "n_open" in a
    # meta now includes detection_auc, base_rate, has_duration
    assert res["meta"]["n_open"] >= 0
    assert res["meta"]["has_duration"] is True  # _make_duration_dataset has duration
    assert res["meta"].get("detection_auc") is not None
    assert res["meta"].get("base_rate") is not None


def test_predict_open_unavailable_when_detection_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_detection_dataset(tmp_path)
    from app.services.ml import predict_open
    res = predict_open("ds_det", {"available": False, "reason": "x"},
                        {"available": False, "reason": "y"}, limit=25)
    assert res["available"] is False
    assert "reason" in res


# ---------------------------------------------------------------------------
# Task 3 — router + findings_from_predictions
# ---------------------------------------------------------------------------

def test_router_predict_returns_shape_on_baked_dataset(monkeypatch, tmp_path):
    """Bakes joblib bundles to disk (like scripts/train_models.py would), then
    hits GET /{dataset_id}/predict and checks the loaded-bundle predict shape."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_duration_dataset(tmp_path, dataset_id="ds_baked")
    from app.services import ml
    from app.services.ml import train_detection, train_duration

    det = train_detection("ds_baked")
    dur = train_duration("ds_baked")
    models_dir = store.dataset_dir("ds_baked") / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump(det, models_dir / "detection.joblib")
    joblib.dump(dur, models_dir / "duration.joblib")

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/predict/ds_baked/predict")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert len(body["flagged"]) > 0
    assert body["by_area"]


def test_router_predict_unavailable_when_no_baked_model(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_detection_dataset(tmp_path, dataset_id="ds_unbaked")
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/predict/ds_unbaked/predict")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert "reason" in body


def test_router_predict_404_when_dataset_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/predict/does-not-exist/predict")
    assert resp.status_code == 404


def test_findings_from_predictions_shapes_a_finding():
    from app.services.insights import findings_from_predictions
    pred = {
        "available": True,
        "flagged": [
            {"id": "FIR1", "detection_prob": 0.12, "predicted_days": 95, "stall": True,
             "factors": ["high report delay", "no named accused"]},
            {"id": "FIR2", "detection_prob": 0.18, "predicted_days": 40, "stall": False,
             "factors": ["Cybercrime"]},
        ],
        "by_area": [{"area": "AreaA", "predicted_detection_rate": 0.4, "n_open": 10}],
        "meta": {"n_open": 12},
    }
    out = findings_from_predictions(pred)
    assert len(out) >= 1
    f = out[0]
    assert f["type"] == "predicted_undetected"
    assert "open case" in f["title"].lower()
    assert 0 <= f["severity"] <= 100
    assert f["drill"]["surface"] == "dashboard"
    assert f["suggested_action"]
    # a second finding for stall risk since one flagged case has stall=True
    assert any(x["type"] == "predicted_stall" for x in out)


def test_findings_from_predictions_empty_when_unavailable():
    from app.services.insights import findings_from_predictions
    assert findings_from_predictions({"available": False, "reason": "no model"}) == []
    assert findings_from_predictions({"available": True, "flagged": []}) == []
    assert findings_from_predictions(None) == []
