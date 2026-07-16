"""Crime Domain Pack — enriches a generic manifest when the data looks like
crime records (FIRs, police stations, IPC/BNS sections, accused/victims).

A domain pack never replaces the generic engine; it layers curated KPIs,
charts, and vocabulary on top of the auto-generated manifest.
"""

from __future__ import annotations

from app.models.manifest import ChartSpec, DatasetManifest, KpiSpec, SemanticRole

CRIME_SIGNALS = (
    "fir", "crime", "offence", "accused", "victim", "police_station",
    "ipc", "bns", "modus", "complainant", "arrest",
)


def looks_like_crime_data(manifest: DatasetManifest) -> bool:
    haystack = " ".join(
        [t.name for t in manifest.tables]
        + [c.name for t in manifest.tables for c in t.columns]
    ).lower()
    hits = sum(1 for s in CRIME_SIGNALS if s in haystack)
    return hits >= 2


def apply_if_match(manifest: DatasetManifest) -> bool:
    if not looks_like_crime_data(manifest):
        return False
    manifest.domain_pack = "crime"

    t = manifest.primary_table()
    if not t:
        return True
    time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
    status = t.first_by_role(SemanticRole.STATUS)

    if status and not any(k.id == "open_cases" for k in manifest.kpis):
        open_vals = [
            v["value"]
            for v in status.stats.top_values
            if isinstance(v["value"], str)
            and any(s in v["value"].lower() for s in ("open", "pending", "investigation"))
        ]
        if open_vals:
            manifest.kpis.append(
                KpiSpec(
                    id="open_cases",
                    title="Open Cases",
                    table=t.name,
                    agg="count",
                    filters={status.name: open_vals},
                )
            )

    gravity = next((c for c in t.columns if c.name == "gravity"), None)
    if gravity and not any(k.id == "heinous_cases" for k in manifest.kpis):
        manifest.kpis.append(KpiSpec(
            id="heinous_cases", title="Heinous Cases", table=t.name, agg="count",
            filters={"gravity": ["Heinous"]}))

    if gravity and status and not any(k.id == "pending_cases" for k in manifest.kpis):
        pend = [v["value"] for v in status.stats.top_values
                if isinstance(v["value"], str)
                and any(s in v["value"].lower() for s in ("investigation", "pending", "open"))]
        if pend:
            manifest.kpis.append(KpiSpec(
                id="pending_cases", title="Pending Investigation", table=t.name,
                agg="count", filters={status.name: pend}))

    if time_col and not any(c.id == "hour_heatmap" for c in manifest.charts):
        manifest.charts.append(
            ChartSpec(
                id="hour_heatmap",
                title="Time-of-Day Pattern",
                kind="bar",
                table=t.name,
                dimension=f"hour({time_col.name})",
            )
        )

    if manifest.entities and not any(c.id == "network" for c in manifest.charts):
        manifest.charts.append(
            ChartSpec(id="network", title="Criminal Network", kind="network", table=t.name)
        )

    manifest.notes = (
        "Crime Pack active: drill-down (district → station), hotspot analysis, "
        "network/link analysis, repeat-offender tracking, and agent playbooks enabled."
    )
    return True
