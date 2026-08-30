import json

import pytest

from app.core import store
from app.services import investigations as svc


def _dataset(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({
        "id": "demo", "name": "Demo", "domain_pack": "generic", "created_at": "2026-01-01T00:00:00Z",
        "tables": [], "relations": [], "entities": [], "kpis": [], "charts": [], "notes": "",
    }))
    return "demo"


def test_card_lifecycle_and_bounds(monkeypatch, tmp_path):
    dataset = _dataset(monkeypatch, tmp_path)
    card = svc.create_card(dataset, {"title": "Mysuru watch", "kind": "area", "target": "Mysuru", "state": {"area": "Mysuru"}})
    assert card["status"] == "new"
    updated = svc.update_card(dataset, card["id"], {"status": "reviewing", "priority": "high", "owner": "Analyst", "notes": "Verify trend"})
    assert updated["status"] == "reviewing" and updated["priority"] == "high"
    assert svc.list_cards(dataset)[0]["id"] == card["id"]
    assert svc.delete_card(dataset, card["id"]) is True
    with pytest.raises(ValueError, match="notes"):
        svc.create_card(dataset, {"title": "x", "kind": "area", "notes": "x" * 2001})
    with pytest.raises(ValueError, match="state.area"):
        svc.create_card(dataset, {"title": "x", "kind": "area", "state": {"area": "x" * 121}})
    bounded = svc.create_card(dataset, {"title": "safe", "kind": "area", "state": {"area": "Mysuru", "frame": 3, "zoom": 9, "category": ["bad"]}})
    assert bounded["state"] == {"area": "Mysuru", "frame": 3}


def test_watch_evaluation_is_idempotent(monkeypatch, tmp_path):
    dataset = _dataset(monkeypatch, tmp_path)
    monkeypatch.setattr(svc.temporal, "compare_periods", lambda *a, **k: {
        "available": True, "delta": {"percent": 42.0}, "dataset_version": "v1",
        "evidence_id": "temporal:1", "window": {"current": {"from": "2026-01-01", "to": "2026-02-01"}},
    })
    rule = svc.create_rule(dataset, {"name": "Robbery rise", "metric": "percent_change", "operator": "gte", "threshold": 25, "from_date": "2026-01-01", "to_date": "2026-02-01", "enabled": True})
    first = svc.evaluate_rule(dataset, rule["id"])
    second = svc.evaluate_rule(dataset, rule["id"])
    assert first["matched"] is True and first["created"] is True
    assert second["matched"] is True and second["created"] is False
    assert len(svc.list_events(dataset)) == 1


def test_watch_rule_update_disable_and_delete(monkeypatch, tmp_path):
    dataset = _dataset(monkeypatch, tmp_path)
    rule = svc.create_rule(dataset, {
        "name": "Robbery rise", "metric": "percent_change", "operator": "gte",
        "threshold": 25, "from_date": "2026-01-01", "to_date": "2026-02-01", "enabled": True,
    })

    updated = svc.update_rule(dataset, rule["id"], {"name": "Priority watch", "threshold": 40, "enabled": False})
    assert updated["name"] == "Priority watch"
    assert updated["threshold"] == 40
    assert updated["enabled"] is False
    with pytest.raises(ValueError, match="disabled"):
        svc.evaluate_rule(dataset, rule["id"])
    assert svc.delete_rule(dataset, rule["id"]) is True
    assert svc.list_rules(dataset) == []


def test_tracker_rejects_unsafe_dataset_ids_and_non_boolean_enabled(monkeypatch, tmp_path):
    _dataset(monkeypatch, tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.list_cards("..")
    with pytest.raises(ValueError, match="enabled"):
        svc.create_rule("demo", {
            "name": "Bad boolean", "metric": "percent_change", "operator": "gte", "threshold": 1,
            "from_date": "2026-01-01", "to_date": "2026-02-01", "enabled": "false",
        })
