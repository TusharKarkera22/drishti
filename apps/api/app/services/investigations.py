"""Bounded demo-instance investigation cards and deterministic watch rules."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from app.core import store
from app.services import temporal

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
STATUSES = {"new", "reviewing", "actioned", "resolved"}
PRIORITIES = {"low", "medium", "high", "critical"}
KINDS = {"area", "hotspot", "entity", "alert", "finding", "mission"}
SAFE_STATE_KEYS = {"investigation", "area", "category", "node", "from", "to", "band", "overlay", "frame"}
MAX_STATE_TEXT = 120


def _lock(dataset_id: str) -> threading.RLock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(dataset_id, threading.RLock())


def _path(dataset_id: str, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", dataset_id) or ".." in dataset_id:
        raise FileNotFoundError("dataset not found")
    store.load_manifest(dataset_id)
    return store.dataset_dir(dataset_id) / name


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(path: Path, value: list[dict]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)


def _text(value: Any, field: str, limit: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def list_cards(dataset_id: str) -> list[dict]:
    with _lock(dataset_id):
        return _load(_path(dataset_id, "investigations.json"))[::-1]


def create_card(dataset_id: str, payload: dict) -> dict:
    kind = str(payload.get("kind", "finding"))
    if kind not in KINDS:
        raise ValueError("unsupported investigation kind")
    state = payload.get("state") or {}
    if not isinstance(state, dict):
        raise ValueError("state must be an object")
    safe_state: dict[str, str | int] = {}
    for key, value in state.items():
        if key not in SAFE_STATE_KEYS:
            continue
        if key == "frame":
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
                safe_state[key] = value
            continue
        if isinstance(value, str):
            safe_state[key] = _text(value, f"state.{key}", MAX_STATE_TEXT)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    card = {
        "id": uuid.uuid4().hex[:12], "title": _text(payload.get("title"), "title", 160, required=True),
        "kind": kind, "target": _text(payload.get("target"), "target", 160),
        "status": "new", "priority": str(payload.get("priority", "medium")),
        "owner": _text(payload.get("owner"), "owner", 80), "notes": _text(payload.get("notes"), "notes", 2000),
        "state": safe_state, "created_at": now, "updated_at": now,
    }
    if card["priority"] not in PRIORITIES:
        raise ValueError("unsupported priority")
    with _lock(dataset_id):
        path = _path(dataset_id, "investigations.json")
        cards = _load(path)
        if len(cards) >= 500:
            raise ValueError("investigation card limit reached")
        cards.append(card)
        _save(path, cards)
    return card


def update_card(dataset_id: str, card_id: str, payload: dict) -> dict:
    with _lock(dataset_id):
        path = _path(dataset_id, "investigations.json")
        cards = _load(path)
        for card in cards:
            if card["id"] != card_id:
                continue
            if "status" in payload:
                status = str(payload["status"])
                if status not in STATUSES:
                    raise ValueError("unsupported status")
                card["status"] = status
            if "priority" in payload:
                priority = str(payload["priority"])
                if priority not in PRIORITIES:
                    raise ValueError("unsupported priority")
                card["priority"] = priority
            for field, limit in (("title", 160), ("owner", 80), ("notes", 2000)):
                if field in payload:
                    card[field] = _text(payload[field], field, limit, required=field == "title")
            card["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            _save(path, cards)
            return card
    raise KeyError(card_id)


def delete_card(dataset_id: str, card_id: str) -> bool:
    with _lock(dataset_id):
        path = _path(dataset_id, "investigations.json")
        cards = _load(path)
        kept = [card for card in cards if card["id"] != card_id]
        if len(kept) == len(cards):
            return False
        _save(path, kept)
        return True


def list_rules(dataset_id: str) -> list[dict]:
    with _lock(dataset_id):
        return _load(_path(dataset_id, "watch_rules.json"))[::-1]


def create_rule(dataset_id: str, payload: dict) -> dict:
    metric, operator = payload.get("metric"), payload.get("operator")
    if metric != "percent_change" or operator not in {"gte", "lte"}:
        raise ValueError("unsupported watch predicate")
    threshold = float(payload.get("threshold"))
    if not -100 <= threshold <= 10000:
        raise ValueError("threshold is outside the supported range")
    enabled = payload.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    rule = {
        "id": uuid.uuid4().hex[:12], "name": _text(payload.get("name"), "name", 120, required=True),
        "metric": metric, "operator": operator, "threshold": threshold,
        "from_date": _text(payload.get("from_date"), "from_date", 10, required=True),
        "to_date": _text(payload.get("to_date"), "to_date", 10, required=True),
        "area": _text(payload.get("area"), "area", 120), "category": _text(payload.get("category"), "category", 120),
        "enabled": enabled, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    with _lock(dataset_id):
        path = _path(dataset_id, "watch_rules.json")
        rules = _load(path)
        if len(rules) >= 100:
            raise ValueError("watch rule limit reached")
        rules.append(rule)
        _save(path, rules)
    return rule


def update_rule(dataset_id: str, rule_id: str, payload: dict) -> dict:
    with _lock(dataset_id):
        path = _path(dataset_id, "watch_rules.json")
        rules = _load(path)
        for rule in rules:
            if rule["id"] != rule_id:
                continue
            if "name" in payload:
                rule["name"] = _text(payload["name"], "name", 120, required=True)
            if "threshold" in payload:
                threshold = float(payload["threshold"])
                if not -100 <= threshold <= 10000:
                    raise ValueError("threshold is outside the supported range")
                rule["threshold"] = threshold
            if "enabled" in payload:
                if not isinstance(payload["enabled"], bool):
                    raise ValueError("enabled must be a boolean")
                rule["enabled"] = payload["enabled"]
            for field in ("from_date", "to_date"):
                if field in payload:
                    rule[field] = _text(payload[field], field, 10, required=True)
            for field in ("area", "category"):
                if field in payload:
                    rule[field] = _text(payload[field], field, 120)
            rule["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            _save(path, rules)
            return rule
    raise KeyError(rule_id)


def delete_rule(dataset_id: str, rule_id: str) -> bool:
    with _lock(dataset_id):
        path = _path(dataset_id, "watch_rules.json")
        rules = _load(path)
        kept = [rule for rule in rules if rule["id"] != rule_id]
        if len(kept) == len(rules):
            return False
        _save(path, kept)
        return True


def list_events(dataset_id: str) -> list[dict]:
    with _lock(dataset_id):
        return _load(_path(dataset_id, "watch_events.json"))[::-1]


def evaluate_rule(dataset_id: str, rule_id: str) -> dict:
    with _lock(dataset_id):
        rule = next((item for item in _load(_path(dataset_id, "watch_rules.json")) if item["id"] == rule_id), None)
        if not rule:
            raise KeyError(rule_id)
        if not rule["enabled"]:
            raise ValueError("watch rule is disabled")
        result = temporal.compare_periods(dataset_id, rule["from_date"], rule["to_date"], area=rule["area"] or None, category=rule["category"] or None)
        value = result.get("delta", {}).get("percent")
        matched = value is not None and (value >= rule["threshold"] if rule["operator"] == "gte" else value <= rule["threshold"])
        fingerprint = hashlib.sha256(f'{rule_id}|{result.get("dataset_version")}|{result.get("window")}'.encode()).hexdigest()[:20]
        path = _path(dataset_id, "watch_events.json")
        events = _load(path)
        existing = next((event for event in events if event["fingerprint"] == fingerprint), None)
        if existing:
            return {**existing, "created": False}
        event = {"id": uuid.uuid4().hex[:12], "rule_id": rule_id, "rule_name": rule["name"], "matched": matched,
                 "value": value, "threshold": rule["threshold"], "evidence_id": result.get("evidence_id"),
                 "dataset_version": result.get("dataset_version"), "window": result.get("window"),
                 "fingerprint": fingerprint, "at": dt.datetime.now(dt.timezone.utc).isoformat()}
        events.append(event)
        _save(path, events[-1000:])
        return {**event, "created": True}
