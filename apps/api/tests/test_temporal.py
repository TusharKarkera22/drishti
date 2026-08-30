import pandas as pd
import pytest

from app.core import store
from app.services.profiler import build_manifest


def _seed(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    dataset_id = "temporal"
    directory = tmp_path / dataset_id
    directory.mkdir()
    days = pd.date_range("2026-01-01", periods=60, freq="D")
    rows = []
    for day in days:
        n = 2 if day < pd.Timestamp("2026-01-31") else 4
        for index in range(n):
            rows.append({
                "occurred_at": day + pd.Timedelta(hours=index % 24),
                "district": "Mysuru" if index % 2 == 0 else "Bengaluru",
                "crime_type": "Robbery" if index % 2 == 0 else "Fraud",
                "latitude": 12.97 + (index % 2) * 0.4,
                "longitude": 77.59 + (index % 2) * 0.4,
            })
    pd.DataFrame(rows).to_parquet(directory / "events.parquet", index=False)
    con = store.connect(dataset_id)
    manifest = build_manifest(con, ["events"], name="Temporal", dataset_id=dataset_id)
    con.close()
    store.save_manifest(manifest)
    return dataset_id


def test_compare_equal_windows_and_frames(monkeypatch, tmp_path):
    from app.services.temporal import compare_periods

    dataset_id = _seed(monkeypatch, tmp_path)
    result = compare_periods(dataset_id, "2026-01-31", "2026-03-02", frame_days=10)

    assert result["available"] is True
    assert result["current"]["rows"] == 120
    assert result["previous"]["rows"] == 60
    assert result["delta"]["absolute"] == 60
    assert result["delta"]["percent"] == 100.0
    assert len(result["frames"]) == 3
    assert {cell["change"] for cell in result["frames"][0]["cells"]} <= {"emerging", "persistent", "declining"}
    assert result["window"]["current"] == {"from": "2026-01-31", "to": "2026-03-02"}
    assert result["dataset_version"]
    assert result["evidence_id"].startswith("temporal:")


def test_compare_rejects_invalid_or_excessive_windows(monkeypatch, tmp_path):
    from app.services.temporal import compare_periods

    dataset_id = _seed(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="before"):
        compare_periods(dataset_id, "2026-02-01", "2026-02-01")
    with pytest.raises(ValueError, match="366"):
        compare_periods(dataset_id, "2024-01-01", "2026-01-01")


def test_compare_missing_history_is_explicit(monkeypatch, tmp_path):
    from app.services.temporal import compare_periods

    dataset_id = _seed(monkeypatch, tmp_path)
    result = compare_periods(dataset_id, "2026-01-01", "2026-01-08", frame_days=7)
    assert result["available"] is False
    assert result["reason"] == "insufficient prior history"
    assert result["current"]["rows"] > 0
    assert result["previous"]["rows"] == 0


def test_compare_applies_context_filters_to_totals_groups_and_frames(monkeypatch, tmp_path):
    from app.services.temporal import compare_periods

    dataset_id = _seed(monkeypatch, tmp_path)
    result = compare_periods(dataset_id, "2026-01-31", "2026-03-02", area="Mysuru", category="Robbery")
    assert result["current"]["rows"] == 60
    assert result["previous"]["rows"] == 30
    assert [row["key"] for row in result["areas"]] == ["Mysuru"]
    assert [row["key"] for row in result["categories"]] == ["Robbery"]
    assert sum(frame["rows"] for frame in result["frames"]) == 60
