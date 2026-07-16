"""Automated sentinel: a background loop that scans every dataset for new
statistical spikes and persists them as alerts — agentic automation that runs
without a human asking. Alerts live in {dataset}/alerts.jsonl next to the
agent-run memory.

On Catalyst the same scan is also exposed as POST /api/alerts/{id}/scan so a
Catalyst Cron + serverless function can drive it instead of the in-process
loop (see docs/deploy_catalyst.md).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import uuid

from app.core import store
from app.models.manifest import SemanticRole
from app.services import analytics

log = logging.getLogger("lens.alerts")

SCAN_INTERVAL_S = int(os.environ.get("ALERT_SCAN_INTERVAL_S", 6 * 3600))
Z_THRESHOLD = 3.0


def _alerts_path(dataset_id: str):
    return store.dataset_dir(dataset_id) / "alerts.jsonl"


def list_alerts(dataset_id: str, limit: int = 100) -> list[dict]:
    path = _alerts_path(dataset_id)
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    return [json.loads(l) for l in lines[-limit:]][::-1]


def mark_read(dataset_id: str, alert_id: str) -> bool:
    path = _alerts_path(dataset_id)
    if not path.exists():
        return False
    alerts = [json.loads(l) for l in path.read_text().strip().splitlines()]
    hit = False
    for a in alerts:
        if a["id"] == alert_id or alert_id == "all":
            a["read"] = True
            hit = True
    if hit:
        path.write_text("".join(json.dumps(a) + "\n" for a in alerts))
    return hit


def scan_dataset(dataset_id: str) -> list[dict]:
    """Run spike detection and append alerts not already on file. Returns the
    newly created alerts."""
    manifest = store.load_manifest(dataset_id)
    t = manifest.primary_table()
    if not t:
        return []
    time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
    if not time_col:
        return []
    cat = t.first_by_role(SemanticRole.CATEGORY)
    area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
    res = analytics.spike_alerts(
        dataset_id, t, time_col.name,
        category_col=cat.name if cat else None,
        area_col=area.name if area else None,
        window_days=28, z_threshold=Z_THRESHOLD,
    )

    existing = {(a.get("area"), a.get("category")) for a in list_alerts(dataset_id, limit=1000)}
    new: list[dict] = []
    for s in res.get("alerts", []):
        area_v = s.get(area.name) if area else None
        cat_v = s.get(cat.name) if cat else None
        if (area_v, cat_v) in existing:
            continue
        title_what = cat_v or "Activity"
        title_where = f" in {area_v}" if area_v else ""
        new.append({
            "id": uuid.uuid4().hex[:10],
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kind": "spike",
            "area": area_v,
            "category": cat_v,
            "z_score": s["z_score"],
            "pct_change": s.get("pct_change"),
            "baseline_daily": s["baseline_daily"],
            "recent_daily": s["recent_daily"],
            "title": f"{title_what} spiking{title_where}: "
                     f"+{s.get('pct_change')}% vs baseline (z={s['z_score']})",
            "read": False,
        })
    if new:
        with _alerts_path(dataset_id).open("a") as f:
            for a in new:
                f.write(json.dumps(a) + "\n")
    return new


def scan_all() -> dict[str, int]:
    out = {}
    for m in store.list_datasets():
        try:
            out[m.id] = len(scan_dataset(m.id))
        except Exception as e:  # one bad dataset must not kill the loop
            log.warning("alert scan failed for %s: %s", m.id, e)
    return out


async def scan_loop() -> None:
    while True:
        try:
            created = await asyncio.to_thread(scan_all)
            if any(created.values()):
                log.info("sentinel created alerts: %s", created)
        except Exception as e:
            log.warning("alert scan loop error: %s", e)
        await asyncio.sleep(SCAN_INTERVAL_S)
