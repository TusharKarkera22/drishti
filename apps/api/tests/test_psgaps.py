"""PS-2 Coverage Gap features — TDD tests.

Covers:
  Task 1 — four analytics functions (spatiotemporal_clusters,
             socioeconomic_correlation, emerging_typologies, mo_signatures)
  Task 2 — four finding builders (findings_from_spatiotemporal,
             findings_from_correlation, findings_from_typology, findings_from_mo)

Seed technique mirrors test_view_resolution.py: write parquet + manifest.json
under a tmp_path, then monkeypatch store.DATA_DIR.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app.core import store
from app.models.manifest import (
    ColumnSpec,
    DatasetManifest,
    TableSpec,
)
from app.models.manifest import SemanticRole as SR

# ---------------------------------------------------------------------------
# Shared seed helper (mirrors test_view_resolution._seed)
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
# Task 1a — spatiotemporal_clusters
# ---------------------------------------------------------------------------

def _make_spatiotemporal_dataset(tmp_path):
    """Plant a strong time concentration: Theft in AreaA is almost entirely
    Night-time (00–05), with n>=20 rows. Other combos are sparse."""
    rows = []
    # Theft × AreaA × Night: 30 rows with hours 2–4
    for i in range(30):
        rows.append({"ts": f"2025-01-{(i % 28) + 1:02d} 02:30:00",
                     "area": "AreaA", "cat": "Theft", "id": f"ID{i}"})
    # Theft × AreaA × Morning: only 3 rows (below min_n)
    for i in range(3):
        rows.append({"ts": "2025-02-01 08:00:00",
                     "area": "AreaA", "cat": "Theft", "id": f"IDM{i}"})
    # Robbery × AreaB × Evening: 25 rows
    for i in range(25):
        rows.append({"ts": f"2025-01-{(i % 28) + 1:02d} 20:00:00",
                     "area": "AreaB", "cat": "Robbery", "id": f"IDR{i}"})
    df = pd.DataFrame(rows)
    manifest = DatasetManifest(id="ds_st", name="st", tables=[
        TableSpec(name="events", is_primary=True, columns=[
            _col("ts", SR.TIMESTAMP),
            _col("area", SR.ADMIN_AREA_1),
            _col("cat", SR.CATEGORY),
            _col("id", SR.ID),
        ])
    ])
    _seed(tmp_path, "ds_st", {"events": df}, manifest)
    return manifest


def test_spatiotemporal_clusters_finds_night_concentration(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_spatiotemporal_dataset(tmp_path)
    from app.services.analytics import spatiotemporal_clusters
    t = DatasetManifest.model_validate_json(
        (tmp_path / "ds_st" / "manifest.json").read_text()
    ).primary_table()
    res = spatiotemporal_clusters("ds_st", t, "ts", "area", "cat", min_n=5, min_share=0.50)
    assert res["available"] is True
    clusters = res["clusters"]
    assert len(clusters) > 0
    # Theft/AreaA must surface as Night
    theft_a = next((c for c in clusters if c["category"] == "Theft" and c["area"] == "AreaA"), None)
    assert theft_a is not None, f"Expected Theft/AreaA cluster, got {clusters}"
    assert theft_a["band"] == "Night"
    assert theft_a["share"] >= 0.50


def test_spatiotemporal_clusters_unavailable_when_no_time_col(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    from app.services.analytics import spatiotemporal_clusters
    t = TableSpec(name="t", is_primary=True, columns=[
        _col("area", SR.ADMIN_AREA_1), _col("cat", SR.CATEGORY),
    ])
    res = spatiotemporal_clusters("ds_st", t, None, "area", "cat")
    assert res["available"] is False
    assert "reason" in res


# ---------------------------------------------------------------------------
# Task 1b — socioeconomic_correlation
# ---------------------------------------------------------------------------

def _make_socioeconomic_dataset(tmp_path):
    """5 areas; urbanization_pct deliberately chosen so per-lakh rate correlates
    positively with urbanization (r should be ~1.0 on this linear relationship)."""
    areas = ["A", "B", "C", "D", "E"]
    # Urban areas have more crime
    urbanization = [20.0, 40.0, 60.0, 80.0, 90.0]
    population = [50000, 60000, 70000, 80000, 90000]
    # crime count scales with urbanization
    crime_count = [u * 10 for u in urbanization]

    events = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=int(sum(crime_count)), freq="h"),
        "area": [a for a, c in zip(areas, crime_count) for _ in range(int(c))],
        "cat": "Theft",
        "id": range(int(sum(crime_count))),
    })
    demo = pd.DataFrame({
        "area": areas,
        "population": population,
        "urbanization_pct": urbanization,
    })
    manifest = DatasetManifest(id="ds_se", name="se", tables=[
        TableSpec(name="events", is_primary=True, columns=[
            _col("ts", SR.TIMESTAMP),
            _col("area", SR.ADMIN_AREA_1),
            _col("cat", SR.CATEGORY),
            _col("id", SR.ID),
        ]),
        TableSpec(name="demo", columns=[
            _col("area", SR.ADMIN_AREA_1),
            ColumnSpec(name="population", dtype="float", semantic_role=SR.MEASURE),
            ColumnSpec(name="urbanization_pct", dtype="float", semantic_role=SR.MEASURE),
        ]),
    ])
    _seed(tmp_path, "ds_se", {"events": events, "demo": demo}, manifest)
    return manifest


def test_socioeconomic_correlation_positive_urbanization(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    manifest = _make_socioeconomic_dataset(tmp_path)
    from app.services.analytics import socioeconomic_correlation
    res = socioeconomic_correlation("ds_se", manifest, "area", min_areas=3)
    assert res["available"] is True
    corrs = res["correlations"]
    urb_corr = next((c for c in corrs if c["factor"] == "urbanization_pct"), None)
    assert urb_corr is not None, f"urbanization_pct not in {corrs}"
    assert urb_corr["r"] > 0, f"expected positive r, got {urb_corr['r']}"
    assert urb_corr["direction"] == "positive"


def test_socioeconomic_correlation_includes_points(monkeypatch, tmp_path):
    """Enhancement A: result must include per-area scatter points."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    manifest = _make_socioeconomic_dataset(tmp_path)
    from app.services.analytics import socioeconomic_correlation
    res = socioeconomic_correlation("ds_se", manifest, "area", min_areas=3)
    assert res["available"] is True
    assert "points" in res, "result must include 'points' for scatter plot"
    pts = res["points"]
    # One point per area (5 areas in seed)
    assert len(pts) == 5, f"expected 5 points, got {len(pts)}"
    # Each point has required keys
    for pt in pts:
        assert "area" in pt
        assert "rate_per_lakh" in pt
        assert isinstance(pt["rate_per_lakh"], float)
        assert "urbanization_pct" in pt
        assert "literacy_pct" in pt
        assert "density_per_km2" in pt


def test_socioeconomic_correlation_unavailable_no_demo(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    # Re-use ST dataset which has no demographics table
    _make_spatiotemporal_dataset(tmp_path)
    manifest = DatasetManifest.model_validate_json(
        (tmp_path / "ds_st" / "manifest.json").read_text()
    )
    from app.services.analytics import socioeconomic_correlation
    res = socioeconomic_correlation("ds_st", manifest, "area")
    assert res["available"] is False
    assert "reason" in res


# ---------------------------------------------------------------------------
# Task 1c — emerging_typologies
# ---------------------------------------------------------------------------

def _make_emerging_dataset(tmp_path):
    """Plant 'Cybercrime' with a rising weekly trend over 8 weeks.
    'Robbery' stays flat. 'Theft' slopes down."""
    rows = []
    base = pd.Timestamp("2025-01-01")
    for week in range(8):
        day = base + pd.Timedelta(weeks=week)
        # Cybercrime: 1 per week baseline + week*3 extra (strong positive slope)
        for _ in range(1 + week * 3):
            rows.append({"ts": str(day), "cat": "Cybercrime", "id": f"C{week}_{_}"})
        # Robbery: flat ~5/week
        for _ in range(5):
            rows.append({"ts": str(day), "cat": "Robbery", "id": f"R{week}_{_}"})
        # Theft: declining
        for _ in range(max(0, 10 - week * 2)):
            rows.append({"ts": str(day), "cat": "Theft", "id": f"T{week}_{_}"})
    df = pd.DataFrame(rows)
    manifest = DatasetManifest(id="ds_et", name="et", tables=[
        TableSpec(name="events", is_primary=True, columns=[
            _col("ts", SR.TIMESTAMP),
            _col("cat", SR.CATEGORY),
            _col("id", SR.ID),
        ])
    ])
    _seed(tmp_path, "ds_et", {"events": df}, manifest)
    return manifest


def test_emerging_typologies_cybercrime_ranks_top(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_emerging_dataset(tmp_path)
    from app.services.analytics import emerging_typologies
    t = DatasetManifest.model_validate_json(
        (tmp_path / "ds_et" / "manifest.json").read_text()
    ).primary_table()
    res = emerging_typologies("ds_et", t, "ts", "cat", weeks=8, min_per_week=0.5)
    assert res["available"] is True
    rising = res["rising"]
    assert len(rising) > 0
    assert rising[0]["category"] == "Cybercrime", f"Expected Cybercrime top, got {rising}"
    assert rising[0]["slope"] > 0


def test_emerging_typologies_unavailable_no_cat_col(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    from app.services.analytics import emerging_typologies
    t = TableSpec(name="t", is_primary=True, columns=[_col("ts", SR.TIMESTAMP)])
    res = emerging_typologies("ds_et", t, "ts", None)
    assert res["available"] is False
    assert "reason" in res


# ---------------------------------------------------------------------------
# Task 1d — mo_signatures
# ---------------------------------------------------------------------------

def _make_mo_dataset(tmp_path):
    """Plant a cross-area recurring MO: 'Night vehicle theft' (subtype=VehicleTheft,
    band=Night) spanning AreaA and AreaB with 10+ cases each."""
    rows = []
    for i in range(12):
        rows.append({"ts": f"2025-01-{(i % 28)+1:02d} 01:00:00",
                     "area": "AreaA", "cat": "Theft", "subtype": "VehicleTheft",
                     "id": f"VA{i}"})
    for i in range(10):
        rows.append({"ts": f"2025-01-{(i % 28)+1:02d} 03:00:00",
                     "area": "AreaB", "cat": "Theft", "subtype": "VehicleTheft",
                     "id": f"VB{i}"})
    # Different subtype, single area (should NOT qualify as cross-area)
    for i in range(6):
        rows.append({"ts": "2025-01-01 14:00:00",
                     "area": "AreaC", "cat": "Robbery", "subtype": "StreetRobbery",
                     "id": f"RB{i}"})
    df = pd.DataFrame(rows)
    manifest = DatasetManifest(id="ds_mo", name="mo", tables=[
        TableSpec(name="events", is_primary=True, columns=[
            _col("ts", SR.TIMESTAMP),
            _col("area", SR.ADMIN_AREA_1),
            _col("cat", SR.CATEGORY),
            _col("subtype", SR.SUBCATEGORY),
            _col("id", SR.ID),
        ])
    ])
    _seed(tmp_path, "ds_mo", {"events": df}, manifest)
    return manifest


def test_mo_signatures_cross_area_vehicle_theft(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    _make_mo_dataset(tmp_path)
    from app.services.analytics import mo_signatures
    t = DatasetManifest.model_validate_json(
        (tmp_path / "ds_mo" / "manifest.json").read_text()
    ).primary_table()
    res = mo_signatures("ds_mo", t, min_cases=8, min_areas=2)
    assert res["available"] is True
    sigs = res["signatures"]
    vt = next((s for s in sigs if s["subtype"] == "VehicleTheft"), None)
    assert vt is not None, f"VehicleTheft not found in {sigs}"
    assert vt["band"] == "Night"
    assert vt["n_areas"] >= 2
    assert len(vt["areas"]) >= 2


def test_mo_signatures_unavailable_no_time_col(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    from app.services.analytics import mo_signatures
    t = TableSpec(name="t", is_primary=True, columns=[
        _col("area", SR.ADMIN_AREA_1), _col("subtype", SR.SUBCATEGORY),
    ])
    res = mo_signatures("ds_mo", t)
    assert res["available"] is False
    assert "reason" in res


# ---------------------------------------------------------------------------
# Task 2 — finding builders
# ---------------------------------------------------------------------------

from app.services import insights as ins


# ---- 2a: spatiotemporal ----

_SPATIOTEMPORAL_RESULT = {
    "available": True,
    "clusters": [
        {"category": "Theft", "area": "AreaA", "band": "Night",
         "band_hours": "00–05", "n": 30, "share": 0.85},
        {"category": "Robbery", "area": "AreaB", "band": "Evening",
         "band_hours": "18–23", "n": 25, "share": 0.72},
    ],
}


def test_findings_from_spatiotemporal_returns_correct_type():
    out = ins.findings_from_spatiotemporal(_SPATIOTEMPORAL_RESULT)
    assert len(out) > 0
    f = out[0]
    assert f["type"] == "spatiotemporal"
    assert f["area"] is not None
    assert f["category"] is not None
    assert f["title"]
    assert f["suggested_action"]
    assert f["drill"]["surface"] == "map"
    assert 0 <= f["severity"] <= 100


def test_findings_from_spatiotemporal_severity_bounded():
    out = ins.findings_from_spatiotemporal(_SPATIOTEMPORAL_RESULT)
    for f in out:
        assert 0 <= f["severity"] <= 100


def test_findings_from_spatiotemporal_empty_on_unavailable():
    assert ins.findings_from_spatiotemporal({"available": False, "reason": "no time"}) == []
    assert ins.findings_from_spatiotemporal({"available": True, "clusters": []}) == []
    assert ins.findings_from_spatiotemporal(None) == []


# ---- 2b: correlation ----

_CORRELATION_RESULT = {
    "available": True,
    "correlations": [
        {"factor": "urbanization_pct", "r": 0.87, "n_areas": 7, "direction": "positive"},
        {"factor": "literacy_pct", "r": -0.43, "n_areas": 7, "direction": "negative"},
    ],
    "n_areas": 7,
}


def test_findings_from_correlation_returns_top_one():
    out = ins.findings_from_correlation(_CORRELATION_RESULT)
    assert len(out) == 1  # only top correlation
    f = out[0]
    assert f["type"] == "socio_correlation"
    assert f["title"]
    assert f["suggested_action"]
    assert f["drill"]["surface"] == "dashboard"
    assert 0 <= f["severity"] <= 100


def test_findings_from_correlation_title_contains_factor_and_direction():
    out = ins.findings_from_correlation(_CORRELATION_RESULT)
    f = out[0]
    assert "urbanization_pct" in f["title"] or "urbanization" in f["title"].lower()
    assert "positive" in f["title"].lower() or "positively" in f["title"].lower()


def test_findings_from_correlation_empty_on_unavailable():
    assert ins.findings_from_correlation({"available": False, "reason": "no demo"}) == []
    assert ins.findings_from_correlation({"available": True, "correlations": []}) == []
    assert ins.findings_from_correlation(None) == []


# ---- 2c: typology ----

_TYPOLOGY_RESULT = {
    "available": True,
    "rising": [
        {"category": "Cybercrime", "slope": 3.2, "growth_pct": 145.0, "recent_weekly_avg": 8.5},
        {"category": "Extortion", "slope": 1.1, "growth_pct": 50.0, "recent_weekly_avg": 3.0},
    ],
    "weeks": 8,
}


def test_findings_from_typology_returns_one_to_two():
    out = ins.findings_from_typology(_TYPOLOGY_RESULT)
    assert 1 <= len(out) <= 2
    f = out[0]
    assert f["type"] == "emerging_typology"
    assert f["category"] is not None
    assert f["title"]
    assert f["suggested_action"]
    assert f["drill"]["surface"] == "dashboard"
    assert 0 <= f["severity"] <= 100


def test_findings_from_typology_title_contains_category():
    out = ins.findings_from_typology(_TYPOLOGY_RESULT)
    assert "Cybercrime" in out[0]["title"]


def test_findings_from_typology_empty_on_unavailable():
    assert ins.findings_from_typology({"available": False, "reason": "no col"}) == []
    assert ins.findings_from_typology({"available": True, "rising": []}) == []
    assert ins.findings_from_typology(None) == []


# ---- 2d: MO ----

_MO_RESULT = {
    "available": True,
    "signatures": [
        {"subtype": "VehicleTheft", "band": "Night", "band_hours": "00–05",
         "n": 22, "n_areas": 2, "areas": ["AreaA", "AreaB"],
         "example_ids": ["VA1", "VA2", "VB1"]},
    ],
}


def test_findings_from_mo_returns_correct_type():
    out = ins.findings_from_mo(_MO_RESULT)
    assert len(out) >= 1
    f = out[0]
    assert f["type"] == "mo_signature"
    assert f["title"]
    assert f["suggested_action"]
    assert f["drill"]["surface"] == "network"
    assert 0 <= f["severity"] <= 100


def test_findings_from_mo_title_contains_subtype_and_n():
    out = ins.findings_from_mo(_MO_RESULT)
    f = out[0]
    assert "VehicleTheft" in f["title"] or "vehicle" in f["title"].lower()
    assert "22" in f["title"] or "Night" in f["title"] or "00–05" in f["title"]


def test_findings_from_mo_empty_on_unavailable():
    assert ins.findings_from_mo({"available": False, "reason": "no area"}) == []
    assert ins.findings_from_mo({"available": True, "signatures": []}) == []
    assert ins.findings_from_mo(None) == []


# ---- sev_* functions bounded ----

def test_sev_spatiotemporal_bounded():
    assert 0 <= ins.sev_spatiotemporal(0.0) <= 100
    assert 0 <= ins.sev_spatiotemporal(1.0) <= 100
    assert ins.sev_spatiotemporal(0.8) > ins.sev_spatiotemporal(0.3)


def test_sev_correlation_bounded():
    assert 0 <= ins.sev_correlation(0.0) <= 100
    assert 0 <= ins.sev_correlation(1.0) <= 100
    assert ins.sev_correlation(0.9) > ins.sev_correlation(0.2)


def test_sev_typology_bounded():
    assert 0 <= ins.sev_typology(0) <= 100
    assert 0 <= ins.sev_typology(200) <= 100
    assert ins.sev_typology(100) > ins.sev_typology(20)


def test_sev_mo_bounded():
    assert 0 <= ins.sev_mo(0) <= 100
    assert 0 <= ins.sev_mo(100) <= 100
    assert ins.sev_mo(20) > ins.sev_mo(5)
