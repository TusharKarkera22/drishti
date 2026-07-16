"""Enhancement B — Repeat-Offender MO profile endpoint — TDD tests.

Builds a tiny dataset with:
- One accused (person) linked to 3 cases across 2 districts
- Cases have a dominant subtype (VehicleTheft) and a clear peak time (Night)

Seed technique mirrors test_psgaps.py / test_view_resolution.py.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from app.core import store
from app.models.manifest import (
    ColumnSpec,
    DatasetManifest,
    EntitySpec,
    Relation,
    TableSpec,
)
from app.models.manifest import SemanticRole as SR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col(name: str, role: SR, dtype: str = "string") -> ColumnSpec:
    return ColumnSpec(name=name, dtype=dtype, semantic_role=role)


def _seed(tmp_path, dataset_id: str, tables: dict[str, pd.DataFrame],
          manifest: DatasetManifest):
    d = tmp_path / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(d / f"{name}.parquet")
    (d / "manifest.json").write_text(manifest.model_dump_json())


# ---------------------------------------------------------------------------
# Dataset factory
#
# Graph structure:
#   person:P1 --involved_in--> case:C1  (district=DistrictA, subtype=VehicleTheft, ts=2025-01-01 02:00 → Night)
#   person:P1 --involved_in--> case:C2  (district=DistrictB, subtype=VehicleTheft, ts=2025-01-02 03:00 → Night)
#   person:P1 --involved_in--> case:C3  (district=DistrictA, subtype=Robbery,      ts=2025-01-03 14:00 → Afternoon)
#   person:P2 --involved_in--> case:C4  (district=DistrictA, subtype=VehicleTheft, ts=2025-01-04 01:00 → Night)
#   (P2 has only 1 case — not a repeat offender)
# ---------------------------------------------------------------------------

def _make_offender_dataset(tmp_path) -> tuple[str, DatasetManifest]:
    dataset_id = "ds_offender"

    incidents = pd.DataFrame({
        "fir_id":   ["C1",              "C2",              "C3",              "C4"],
        "district": ["DistrictA",       "DistrictB",       "DistrictA",       "DistrictA"],
        "subtype":  ["VehicleTheft",    "VehicleTheft",    "Robbery",         "VehicleTheft"],
        "ts":       ["2025-01-01 02:00", "2025-01-02 03:00", "2025-01-03 14:00", "2025-01-04 01:00"],
    })

    accused = pd.DataFrame({
        "acc_id":   ["P1", "P1", "P1", "P2"],
        "name":     ["Ravi Kumar", "Ravi Kumar", "Ravi Kumar", "Suresh"],
        "case_ref": ["C1", "C2", "C3", "C4"],
    })

    manifest = DatasetManifest(
        id=dataset_id,
        name="offender_test",
        tables=[
            TableSpec(name="incidents", is_primary=True, columns=[
                _col("fir_id",   SR.ID),
                _col("district", SR.ADMIN_AREA_1),
                _col("subtype",  SR.SUBCATEGORY),
                _col("ts",       SR.TIMESTAMP),
            ]),
            TableSpec(name="accused", columns=[
                _col("acc_id",   SR.ID),
                _col("name",     SR.PERSON_NAME),
                _col("case_ref", SR.FOREIGN_KEY),
            ]),
        ],
        entities=[
            EntitySpec(
                name="person",
                table="accused",
                id_column="acc_id",
                label_column="name",
                link_columns=[],
            )
        ],
        relations=[
            Relation(
                from_table="accused",
                from_column="case_ref",
                to_table="incidents",
                to_column="fir_id",
                kind="many_to_one",
            )
        ],
    )

    _seed(tmp_path, dataset_id, {"incidents": incidents, "accused": accused}, manifest)
    return dataset_id, manifest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_offender_profile_repeat_offender(monkeypatch, tmp_path):
    """P1 has 3 cases across 2 districts; top_subtype=VehicleTheft, peak_band=Night."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    dataset_id, manifest = _make_offender_dataset(tmp_path)

    from app.services.graph import build_graph, offender_profile

    g = build_graph(dataset_id, manifest)
    result = offender_profile(g, dataset_id, manifest, "person:P1")

    assert result["node"] == "person:P1"
    assert result["label"] == "Ravi Kumar"
    assert result["case_count"] >= 2, f"expected >=2 cases, got {result['case_count']}"
    assert len(result["districts"]) >= 2, f"expected >=2 districts, got {result['districts']}"
    assert "DistrictA" in result["districts"]
    assert "DistrictB" in result["districts"]
    assert result["mo"]["top_subtype"] == "VehicleTheft", (
        f"expected VehicleTheft as top_subtype, got {result['mo']['top_subtype']}"
    )
    assert result["mo"]["peak_band"] == "Night", (
        f"expected Night as peak_band, got {result['mo']['peak_band']}"
    )
    assert len(result["cases"]) >= 2
    # Each case record has required keys
    for c in result["cases"]:
        assert "fir" in c
        assert "district" in c
        assert "subtype" in c
        assert "band" in c


def test_offender_profile_missing_node_returns_empty(monkeypatch, tmp_path):
    """A node that does not exist must return the empty shape, never raise."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    dataset_id, manifest = _make_offender_dataset(tmp_path)

    from app.services.graph import build_graph, offender_profile

    g = build_graph(dataset_id, manifest)
    result = offender_profile(g, dataset_id, manifest, "person:NONEXISTENT")

    assert result["node"] == "person:NONEXISTENT"
    assert result["label"] is None
    assert result["case_count"] == 0
    assert result["districts"] == []
    assert result["mo"]["top_subtype"] is None
    assert result["mo"]["peak_band"] is None
    assert result["cases"] == []
