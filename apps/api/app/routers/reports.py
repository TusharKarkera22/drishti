"""Digital Crime Handbook — replaces the static annual crime handbook with a
dynamic, manifest-driven bundle: KPIs, area/category tables, monthly trend,
spike alerts, risk board, and network highlights, assembled live from the
dataset. The /report page renders it on screen and prints it to PDF.
"""

from __future__ import annotations

import datetime
import json

from fastapi import APIRouter, HTTPException

from app.core import rescache, store
from app.models.manifest import SemanticRole
from app.routers import graph as graph_router
from app.routers.query import Measure, QueryRequest, run_query
from app.services import analytics as analytics_svc
from app.services import llm

router = APIRouter()


def _ctx(dataset_id: str):
    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    t = manifest.primary_table()
    if not t:
        raise HTTPException(400, "dataset has no tables")
    return manifest, t


@router.get("/{dataset_id}/handbook")
def handbook(dataset_id: str, period: str | None = None, refresh: bool = False) -> dict:
    manifest, t = _ctx(dataset_id)

    def compute():
        time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
        area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
        cat = t.first_by_role(SemanticRole.CATEGORY)
        status = t.first_by_role(SemanticRole.STATUS)
        money = t.first_by_role(SemanticRole.MONEY)

        filters: dict = {}
        if period and time_col:
            filters[time_col.name] = {"from": f"{period}-01-01 00:00:00",
                                      "to": f"{period}-12-31 23:59:59"}

        def q(**kw) -> dict | None:
            """One handbook section must never sink the whole document."""
            req = QueryRequest(table=t.name, filters={**filters, **kw.pop("filters", {})}, **kw)
            try:
                return run_query(dataset_id, req)
            except Exception:
                return None

        measures = [Measure(agg="count", alias="count")]
        if money:
            measures.append(Measure(agg="sum", column=money.name, alias="total_value"))

        out: dict = {
            "dataset": manifest.name,
            "domain_pack": manifest.domain_pack,
            "period": period or "full",
            "time_column": time_col.name if time_col else None,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # KPI strip — reuses the manifest's curated KPIs (domain packs add theirs)
        kpis = []
        for k in manifest.kpis:
            req = QueryRequest(
                table=k.table,
                measures=[Measure(agg=k.agg, column=k.column, alias="v")],
                filters={**(filters if k.table == t.name else {}), **k.filters},
            )
            try:
                res = run_query(dataset_id, req)
                kpis.append({"id": k.id, "title": k.title, "value": res["rows"][0][0]})
            except Exception:
                continue
        out["kpis"] = kpis

        demo: dict = {}
        if area:
            out["by_area"] = q(dimensions=[area.name], measures=measures,
                               order_by="count", limit=100)
            out["area_label"] = area.label
            demo = analytics_svc.load_demographics(dataset_id, manifest, area.name)
            if demo:
                out["demographics"] = demo
        if cat:
            out["by_category"] = q(dimensions=[cat.name], measures=measures,
                                   order_by="count", limit=50)
            out["category_label"] = cat.label
        if status:
            out["by_status"] = q(dimensions=[status.name], order_by="count", limit=20)
        if time_col:
            out["monthly_trend"] = q(time_dimension=time_col.name, time_grain="month")
            try:
                out["spikes"] = analytics_svc.spike_alerts(
                    dataset_id, t, time_col.name,
                    category_col=cat.name if cat else None,
                    area_col=area.name if area else None,
                    window_days=28, z_threshold=2.5,
                )["alerts"][:10]
                if area:
                    out["risk"] = analytics_svc.area_risk(
                        dataset_id, t, time_col.name, area.name,
                        horizon_days=7, demographics=demo or None,
                    )
            except Exception:
                pass

        # Network highlights only when the graph is already cached — a handbook
        # request must never block on a cold multi-second graph build. Match
        # the EXACT current dataset version — a stale prefix match would serve
        # a pre-append graph summary and bake it into freshly-cached handbooks.
        net_key = f"{dataset_id}@{rescache.dataset_version(manifest)}"
        summ = graph_router._summary_cache.get(net_key)
        if summ is not None:
            out["network"] = {
                "nodes": summ["nodes"], "edges": summ["edges"],
                "repeat_offenders": summ["repeat_offenders"][:10],
                "key_players": summ["key_players"][:10],
            }
        return {k: v for k, v in out.items() if v is not None}

    params = {"period": period}
    return rescache.get_or_compute(dataset_id, "handbook", params, compute, refresh)


@router.get("/{dataset_id}/handbook/summary")
def handbook_summary(dataset_id: str, period: str | None = None,
                     language: str = "en") -> dict:
    """LLM-written executive summary of the handbook bundle (optional add-on;
    the handbook itself never depends on the LLM being reachable)."""
    data = handbook(dataset_id, period)
    digest = json.dumps(
        {k: data[k] for k in ("kpis", "spikes", "risk", "by_category") if k in data},
        default=str,
    )[:6000]
    lang_line = (" Write the summary in Kannada (ಕನ್ನಡ); keep identifiers and "
                 "place names as-is." if language == "kn" else "")
    try:
        msg = llm.chat([
            {"role": "system", "content":
                "You write the executive summary of an annual crime statistics "
                "handbook for senior police leadership. 4-6 crisp sentences, "
                "grounded ONLY in the numbers provided — never invent figures."
                + lang_line},
            {"role": "user", "content": digest},
        ])
        return {"summary": msg.get("content") or "", "language": language}
    except llm.LLMError as e:
        raise HTTPException(503, str(e))
