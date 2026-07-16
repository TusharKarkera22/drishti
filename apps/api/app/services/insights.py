"""Insights ("Command Brief"): compose the signals LENS already computes —
spikes, area-risk, network hubs, anomalies, data-quality gaps — into ranked,
plain-language findings, an explainable forecast, a self-backtest credibility
number, and a grounded LLM narrative. The LLM is INJECTED (llm_fn) so the brief
is unit-testable; everything else is deterministic and reuses services.analytics
+ services.digest. Never reasons over raw rows beyond a sampled digest."""
from __future__ import annotations

import datetime
import json
import math

import numpy as np
import pandas as pd

from app.core import store
from app.models.manifest import SemanticRole
from app.services import analytics, digest as digest_mod


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


# ---- severity (transparent, bounded heuristics; constants are tunable) ----

def sev_spike(z, z_threshold=2.5):
    return int(round(_clip(40 + (z - z_threshold) * 15, 0, 100)))


def sev_risk(risk_score):
    return int(round(_clip(risk_score, 0, 100)))


def sev_repeat_offender(case_count):
    return int(round(_clip(35 + 6 * case_count, 0, 95)))


def sev_anomaly(n_flagged):
    return int(round(_clip(40 + 2 * n_flagged, 0, 85)))


def sev_data_gap(rate):  # rate in 0..1
    return int(round(_clip(30 + rate * 60, 0, 80)))


def sev_spatiotemporal(share):  # share in 0..1
    return int(round(_clip(45 + share * 45, 0, 95)))


def sev_correlation(r):  # r = Pearson correlation coefficient
    return int(round(_clip(40 + abs(r) * 55, 0, 95)))


def sev_typology(growth):  # growth_pct
    return int(round(_clip(45 + growth / 4, 0, 95)))


def sev_mo(n_cases):  # total case count for the signature
    return int(round(_clip(40 + 4 * n_cases, 0, 92)))


def sev_predicted_undetected(n_flagged, avg_risk):  # avg_risk = avg(1 - detection_prob) in 0..1
    return int(round(_clip(35 + n_flagged * 1.5 + avg_risk * 40, 0, 95)))


def sev_predicted_stall(n_stall):
    return int(round(_clip(40 + 5 * n_stall, 0, 90)))


# ---- finding builders (pure: signal output + resolved column names -> findings) ----

def findings_from_spikes(alerts, *, area_col=None, cat_col=None, z_threshold=2.5):
    out = []
    for a in alerts:
        z = float(a.get("z_score", 0))
        area = a.get(area_col) if area_col else None
        cat = a.get(cat_col) if cat_col else None
        pct = a.get("pct_change")
        pct_txt = f"up {pct:.0f}%" if isinstance(pct, (int, float)) else "elevated"
        out.append({
            "id": f"spike:{area}:{cat}",
            "type": "spike",
            "severity": sev_spike(z, z_threshold),
            "title": f"{cat or 'Incidents'} in {area or 'the data'} {pct_txt} vs baseline (z={z:.1f})",
            "evidence": {"z_score": z, "baseline_daily": a.get("baseline_daily"),
                         "recent_daily": a.get("recent_daily"), "pct_change": pct},
            "area": str(area) if area is not None else None,
            "category": str(cat) if cat is not None else None,
            "suggested_action": f"Brief the {area or 'relevant'} unit and check resourcing for "
                                f"{cat or 'this category'}.",
            "drill": {"surface": "dashboard",
                      "params": {k: str(v) for k, v in (("area", area), ("category", cat))
                                 if v is not None}},
        })
    return out


def findings_from_risk(areas, *, top=3):
    out = []
    for a in [x for x in (areas or []) if x.get("trend_slope", 0) > 0][:top]:
        area, fc, rs = a.get("area"), a.get("forecast_daily"), a.get("risk_score")
        fc_txt = f", ~{fc:.0f}/day forecast next week" if isinstance(fc, (int, float)) else ""
        rs_txt = f"{rs:.0f}" if isinstance(rs, (int, float)) else "?"
        out.append({
            "id": f"risk:{area}",
            "type": "rising_risk",
            "severity": sev_risk(rs or 0),
            "title": f"{area} trending up — risk {rs_txt}/100{fc_txt}",
            "evidence": {"risk_score": rs, "recent_daily_avg": a.get("recent_daily_avg"),
                         "trend_slope": a.get("trend_slope"), "forecast_daily": fc,
                         "per_lakh_daily": a.get("per_lakh_daily")},
            "area": str(area) if area is not None else None,
            "category": None,
            "suggested_action": f"Prioritize patrols and resourcing in {area} for the coming week.",
            "drill": {"surface": "map", "params": {"area": str(area)} if area is not None else {}},
        })
    return out


def findings_from_network(summary, *, top=3):
    out = []
    for r in ((summary or {}).get("repeat_offenders") or [])[:top]:
        cc = r.get("case_count", 0)
        out.append({
            "id": f"hub:{r.get('node')}",
            "type": "network_hub",
            "severity": sev_repeat_offender(cc),
            "title": f"{r.get('label')} linked to {cc} cases — possible repeat offender / hub",
            "evidence": {"node": r.get("node"), "case_count": cc},
            "area": None, "category": None,
            "suggested_action": f"Open {r.get('label')}'s ego network and review shared phones/addresses.",
            "drill": {"surface": "network", "params": {"node": str(r.get("node"))}},
        })
    return out


def findings_from_anomalies(anom):
    items = (anom or {}).get("anomalies") or []
    if not items:
        return []
    n = len(items)
    return [{
        "id": "anomaly:batch",
        "type": "anomaly",
        "severity": sev_anomaly(n),
        "title": f"{n} record{'s' if n != 1 else ''} flagged as statistical outliers",
        "evidence": {"count": n, "examples": [i.get("record_id") for i in items[:5]],
                     "top_score": items[0].get("score")},
        "area": None, "category": None,
        "suggested_action": "Review flagged records for data-entry errors or genuinely unusual cases.",
        "drill": {"surface": "dashboard", "params": {}},
    }]


def findings_from_data_gaps(digest, *, threshold=0.10):
    """Surfaces the single worst data-quality gap on a meaningful column. Only
    high null-fraction and malformed-phone columns are flagged (date-parse rate
    is intentionally skipped — it conflates nulls with format issues)."""
    worst = None  # (rate, column, kind)
    for info in (digest or {}).get("columns", []):
        col = info.get("name")
        null_pct = info.get("null_pct")
        if isinstance(null_pct, (int, float)) and null_pct > threshold:
            if worst is None or null_pct > worst[0]:
                worst = (null_pct, col, "missing values")
        plr = info.get("phone_like_rate")
        if isinstance(plr, (int, float)) and 0.3 < plr < 0.9:
            rate = 1 - plr
            if rate > threshold and (worst is None or rate > worst[0]):
                worst = (rate, col, "malformed phone numbers")
    if not worst:
        return []
    rate, col, kind = worst
    return [{
        "id": f"gap:{col}",
        "type": "data_gap",
        "severity": sev_data_gap(rate),
        "title": f"{rate * 100:.0f}% of '{col}' is {kind} — an evidence blind spot",
        "evidence": {"column": col, "issue": kind, "rate": round(float(rate), 3)},
        "area": None, "category": None,
        "suggested_action": f"Run Data Intake to repair '{col}' before relying on it.",
        "drill": {"surface": "intake", "params": {}},
    }]


def findings_from_spatiotemporal(clusters_res):
    """Convert spatiotemporal_clusters output into findings.
    Top-N concentrated (category, area, band) cells become actionable patrol
    recommendations. Returns [] when unavailable or no clusters."""
    if not clusters_res:
        return []
    if not clusters_res.get("available"):
        return []
    clusters = clusters_res.get("clusters") or []
    out = []
    for c in clusters:
        category = c.get("category")
        area = c.get("area")
        band = c.get("band", "")
        band_hours = c.get("band_hours", "")
        share = float(c.get("share", 0))
        n = c.get("n", 0)
        out.append({
            "id": f"spatiotemporal:{category}:{area}:{band}",
            "type": "spatiotemporal",
            "severity": sev_spatiotemporal(share),
            "title": (f"{category} in {area} concentrates {band} {band_hours} "
                      f"({share:.0%} of them) — time-targeted patrols"),
            "evidence": {"category": category, "area": area, "band": band,
                         "band_hours": band_hours, "n": n, "share": share},
            "area": str(area) if area is not None else None,
            "category": str(category) if category is not None else None,
            "suggested_action": (f"Deploy focused patrols in {area} during "
                                 f"{band} ({band_hours}) to intercept {category}."),
            "drill": {"surface": "map",
                      "params": {k: str(v) for k, v in (("area", area), ("category", category))
                                 if v is not None}},
        })
    return out


def findings_from_correlation(corr_res):
    """Convert socioeconomic_correlation output into a finding.
    Only the top correlation (by |r|) becomes a finding — one high-level
    'why behind the where' insight. Returns [] when unavailable or empty."""
    if not corr_res:
        return []
    if not corr_res.get("available"):
        return []
    correlations = corr_res.get("correlations") or []
    if not correlations:
        return []
    top = correlations[0]  # already sorted by abs(r) desc
    factor = top.get("factor", "")
    r = float(top.get("r", 0))
    direction = top.get("direction", "positive")
    n_areas = top.get("n_areas", 0)
    return [{
        "id": f"socio_correlation:{factor}",
        "type": "socio_correlation",
        "severity": sev_correlation(r),
        "title": (f"{factor} {direction}ly correlates with crime rate "
                  f"(r={r:+.2f}) — the 'why' behind the 'where'"),
        "evidence": {"factor": factor, "r": r, "direction": direction,
                     "n_areas": n_areas},
        "area": None,
        "category": None,
        "suggested_action": (f"Target social-intervention budgets at areas with "
                             f"{'high' if direction == 'positive' else 'low'} {factor}."),
        "drill": {"surface": "dashboard", "params": {}},
    }]


def findings_from_typology(typo_res):
    """Convert emerging_typologies output into findings (top 1–2 rising cats).
    Returns [] when unavailable or no rising categories."""
    if not typo_res:
        return []
    if not typo_res.get("available"):
        return []
    rising = typo_res.get("rising") or []
    if not rising:
        return []
    weeks = typo_res.get("weeks", 8)
    out = []
    for r in rising[:2]:
        category = r.get("category")
        growth = float(r.get("growth_pct", 0))
        out.append({
            "id": f"emerging_typology:{category}",
            "type": "emerging_typology",
            "severity": sev_typology(growth),
            "title": (f"{category} is the fastest-emerging typology "
                      f"(+{growth:.0f}% over {weeks} wks)"),
            "evidence": {"category": category, "slope": r.get("slope"),
                         "growth_pct": growth,
                         "recent_weekly_avg": r.get("recent_weekly_avg"),
                         "weeks": weeks},
            "area": None,
            "category": str(category) if category is not None else None,
            "suggested_action": (f"Allocate specialist resources and open a themed "
                                 f"operation for {category} before it peaks."),
            "drill": {"surface": "dashboard",
                      "params": {"category": str(category)} if category else {}},
        })
    return out


def findings_from_mo(mo_res):
    """Convert mo_signatures output into findings (top 1–2 MO signatures).
    Returns [] when unavailable or no signatures."""
    if not mo_res:
        return []
    if not mo_res.get("available"):
        return []
    signatures = mo_res.get("signatures") or []
    if not signatures:
        return []
    out = []
    for s in signatures[:2]:
        subtype = s.get("subtype", "unknown")
        band_hours = s.get("band_hours", "")
        n = s.get("n", 0)
        n_areas = s.get("n_areas", 0)
        out.append({
            "id": f"mo_signature:{subtype}:{s.get('band','')}",
            "type": "mo_signature",
            "severity": sev_mo(n),
            "title": (f"MO signature: {n} {subtype} cases {band_hours} "
                      f"across {n_areas} districts — recurring method, possible single crew"),
            "evidence": {"subtype": subtype, "band": s.get("band"),
                         "band_hours": band_hours, "n": n, "n_areas": n_areas,
                         "areas": s.get("areas", []),
                         "example_ids": s.get("example_ids", [])},
            "area": None,
            "category": None,
            "suggested_action": (f"Cross-reference {subtype} FIRs across "
                                 f"{n_areas} districts for shared suspects/vehicles."),
            "drill": {"surface": "network", "params": {}},
        })
    return out


def findings_from_predictions(pred):
    """Convert services.ml.predict_open output into findings: one headline
    "high risk of going undetected" finding over the flagged OPEN cases, plus
    a second "predicted to stall" finding when any flagged case's predicted
    duration exceeds the training-set p90 (duration model is optional — ksp-
    crime has none, so 'stall' simply never appears). Returns [] when
    unavailable or there's nothing flagged; never raises."""
    if not pred or not pred.get("available"):
        return []
    flagged = pred.get("flagged") or []
    if not flagged:
        return []

    n = len(flagged)
    avg_risk = sum(1 - f.get("detection_prob", 0) for f in flagged) / n
    avg_odds_pct = round((1 - avg_risk) * 100)
    out = [{
        "id": "predicted_undetected:batch",
        "type": "predicted_undetected",
        "severity": sev_predicted_undetected(n, avg_risk),
        "title": (f"{n} open case{'s' if n != 1 else ''} predicted at high risk of going "
                  f"undetected (avg {avg_odds_pct}% detection odds) — prioritise review"),
        "evidence": {"n_flagged": n, "avg_detection_odds_pct": avg_odds_pct,
                     "examples": [f.get("id") for f in flagged[:5]]},
        "area": None, "category": None,
        "suggested_action": "Route the lowest-odds open cases to a senior investigator for review "
                            "— advisory only, human review required.",
        "drill": {"surface": "dashboard", "params": {}},
    }]

    stalling = [f for f in flagged if f.get("stall")]
    if stalling:
        n_stall = len(stalling)
        out.append({
            "id": "predicted_stall:batch",
            "type": "predicted_stall",
            "severity": sev_predicted_stall(n_stall),
            "title": (f"{n_stall} open case{'s' if n_stall != 1 else ''} predicted to stall "
                      f"well past the typical resolution time"),
            "evidence": {"n_stall": n_stall, "examples": [f.get("id") for f in stalling[:5]]},
            "area": None, "category": None,
            "suggested_action": "Escalate these long-running cases for a status review "
                                "— advisory only, human review required.",
            "drill": {"surface": "dashboard", "params": {}},
        })
    return out


def select(findings, *, per_type_cap=3, top=7):
    """Severity-rank, soft-cap each type, and always retain the headline spike
    and rising-risk finding so the top problem is never dropped by the cap."""
    ranked = sorted(findings, key=lambda f: -f["severity"])
    keep, counts, seen = [], {}, set()
    for t in ("spike", "rising_risk"):
        first = next((f for f in ranked if f["type"] == t), None)
        if first and first["id"] not in seen:
            keep.append(first); seen.add(first["id"]); counts[t] = counts.get(t, 0) + 1
    for f in ranked:
        if f["id"] in seen or counts.get(f["type"], 0) >= per_type_cap:
            continue
        keep.append(f); seen.add(f["id"]); counts[f["type"]] = counts.get(f["type"], 0) + 1
        if len(keep) >= top:
            break
    return keep[:top]


# ---- credibility: retrospective capture@k on the data's own history ----

def capture_at_k(daily, *, area_col, day_col="day", n_col="n",
                 window_days=7, max_folds=3, min_history_days=90):
    """At each weekly cutoff, rank areas by their trailing-28-day volume using
    ONLY past data, take the top-k, and measure what share of the next window's
    incidents fell in those areas. Averaged over up to `max_folds` weekly cutoffs.
    A retrospective check on the data's own history — not an accuracy claim."""
    if daily is None or daily.empty:
        return {"available": False, "reason": "no data"}
    df = daily.copy()
    df[day_col] = pd.to_datetime(df[day_col])
    n_areas = int(df[area_col].nunique())
    end, start = df[day_col].max(), df[day_col].min()
    if (end - start).days < min_history_days or n_areas < 5:
        return {"available": False, "reason": "insufficient history"}
    k = max(3, math.ceil(0.2 * n_areas))
    rates = []
    for fold in range(1, max_folds + 1):
        cut = end - pd.Timedelta(days=window_days * fold)
        past = df[df[day_col] <= cut]
        future = df[(df[day_col] > cut) & (df[day_col] <= cut + pd.Timedelta(days=window_days))]
        if past.empty or future.empty:
            continue
        recent = past[past[day_col] > cut - pd.Timedelta(days=28)]
        score = recent.groupby(area_col)[n_col].sum().sort_values(ascending=False)
        flagged = set(score.head(k).index)
        total = float(future[n_col].sum())
        if total > 0:
            hit = float(future[future[area_col].isin(flagged)][n_col].sum())
            rates.append(hit / total)
    if not rates:
        return {"available": False, "reason": "insufficient history"}
    return {"available": True, "capture_rate": round(float(np.mean(rates)), 3),
            "k": k, "folds": len(rates), "window_days": window_days, "n_areas": n_areas}


def confidence(history_days, n_areas):
    if history_days >= 180 and n_areas >= 5:
        return "high"
    if history_days >= 60:
        return "medium"
    return "low"


# ---- narrative: grounded LLM brief with a deterministic fallback ----

def _fallback_brief(insights, language="en"):
    findings = insights.get("findings", [])
    if not findings:
        return "No significant problems detected in this dataset."
    parts = [f"{len(findings)} priority finding{'s' if len(findings) != 1 else ''}.",
             f"Most urgent: {findings[0]['title']}."]
    risk = next((f for f in findings if f["type"] == "rising_risk"), None)
    if risk:
        parts.append(f"Watch: {risk['title']}.")
    gap = next((f for f in findings if f["type"] == "data_gap"), None)
    if gap:
        parts.append(f"Data caveat: {gap['title']}.")
    bt = insights.get("backtest", {})
    if bt.get("available"):
        parts.append("On recent history, the top-risk areas captured "
                     f"{bt['capture_rate'] * 100:.0f}% of the next week's incidents.")
    return " ".join(parts)


def _brief_messages(insights, language):
    payload = {
        "findings": [{"type": f["type"], "severity": f["severity"], "title": f["title"],
                      "area": f.get("area")} for f in insights.get("findings", [])],
        "forecast": (insights.get("forecast") or {}).get("areas", [])[:3],
        "backtest": insights.get("backtest", {}),
    }
    lang = (" Write the brief in Kannada (ಕನ್ನಡ); keep identifiers and place names as-is."
            if language == "kn" else "")
    return [
        {"role": "system", "content":
            "You brief senior police leadership. Write 4-6 crisp sentences, grounded ONLY "
            "in the findings provided — never invent figures. Lead with the most urgent "
            "problem and end with the near-term outlook." + lang},
        {"role": "user", "content": json.dumps(payload, default=str)[:5000]},
    ]


def commander_brief(insights, *, language="en", llm_fn=None):
    """Returns {"brief", "language", "source": "llm"|"fallback"}. `llm_fn` takes a
    messages list and returns text; any failure (or None) yields the deterministic
    fallback so the surface never blanks during a live demo."""
    if llm_fn is None:
        return {"brief": _fallback_brief(insights, language), "language": language, "source": "fallback"}
    try:
        text = llm_fn(_brief_messages(insights, language))
        if not text or not str(text).strip():
            raise ValueError("empty completion")
        return {"brief": str(text).strip(), "language": language, "source": "llm"}
    except Exception:
        return {"brief": _fallback_brief(insights, language), "language": language, "source": "fallback"}


def _load_baked_predictions(dataset_id):
    """Load the baked detection/duration joblib bundles (scripts/train_models.py
    output) and score the OPEN cases — never trains here. Returns None (no
    predicted_* findings contributed) when no detection model was baked for
    this dataset, matching the router's own graceful degradation."""
    import joblib

    from app.services import ml

    models_dir = store.dataset_dir(dataset_id) / "models"
    det_path = models_dir / "detection.joblib"
    if not det_path.exists():
        return None
    det_bundle = joblib.load(det_path)
    dur_path = models_dir / "duration.joblib"
    dur_bundle = joblib.load(dur_path) if dur_path.exists() else None
    return ml.predict_open(dataset_id, det_bundle, dur_bundle, limit=25)


# ---- orchestrator: compose all signals into a findings bundle ----

def _utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def build_insights(dataset_id, *, network_summary=None):
    """Compose all available signals into a ranked findings bundle. Each source
    is independently guarded — a missing role / cold graph / failing model simply
    contributes no findings of that type (graceful degradation, never an error).
    LLM-free: the narrative is produced separately by commander_brief()."""
    manifest = store.load_manifest(dataset_id)  # raises FileNotFoundError -> 404 in router
    t = manifest.primary_table()
    time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
    area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
    cat = t.first_by_role(SemanticRole.CATEGORY)
    area_col = area.name if area else None
    cat_col = cat.name if cat else None

    findings, forecast = [], {}
    backtest = {"available": False, "reason": "no time/area columns"}
    hist_days = 0

    if time_col and area_col:
        try:
            daily = analytics._daily_counts(dataset_id, t.name, time_col.name, [area_col])
            if not daily.empty:
                d = pd.to_datetime(daily["day"])
                hist_days = int((d.max() - d.min()).days)
                backtest = capture_at_k(daily, area_col=area_col)
        except Exception:
            pass

    if time_col:
        try:
            alerts = analytics.spike_alerts(dataset_id, t, time_col.name, category_col=cat_col,
                                            area_col=area_col, window_days=28, z_threshold=2.0)["alerts"]
            findings += findings_from_spikes(alerts, area_col=area_col, cat_col=cat_col, z_threshold=2.0)
        except Exception:
            pass

    if time_col and area_col:
        try:
            demo = analytics.load_demographics(dataset_id, manifest, area_col)
            risk = analytics.area_risk(dataset_id, t, time_col.name, area_col,
                                       horizon_days=7, demographics=demo or None)
            findings += findings_from_risk(risk["areas"], top=3)
            forecast = {
                "horizon_days": 7, "as_of": risk.get("as_of"),
                "demographics_used": risk.get("demographics_used", False),
                "confidence": confidence(hist_days, len(risk["areas"])),
                "areas": [{k: a.get(k) for k in ("area", "forecast_daily", "risk_score",
                                                 "recent_daily_avg", "components", "per_lakh_daily")}
                          for a in risk["areas"][:5]],
            }
        except Exception:
            pass

    try:
        anom = analytics.detect_anomalies(dataset_id, t, contamination=0.01, limit=20)
        findings += findings_from_anomalies(anom)
    except Exception:
        pass

    if network_summary:
        try:
            findings += findings_from_network(network_summary, top=3)
        except Exception:
            pass

    try:
        con = store.connect(dataset_id)
        try:
            df = con.execute(f'SELECT * FROM "{t.name}" LIMIT 20000').df()
        finally:
            con.close()
        id_col = t.first_by_role(SemanticRole.ID)
        dg = digest_mod.profile_digest(df, key_col=id_col.name if id_col else None)
        findings += findings_from_data_gaps(dg)
    except Exception:
        pass

    # ---- PS-2 gap signals ----
    if time_col and area_col and cat_col:
        try:
            st = analytics.spatiotemporal_clusters(
                dataset_id, t, time_col.name, area_col, cat_col)
            findings += findings_from_spatiotemporal(st)
        except Exception:
            pass

    if area_col:
        try:
            corr = analytics.socioeconomic_correlation(dataset_id, manifest, area_col)
            findings += findings_from_correlation(corr)
        except Exception:
            pass

    if time_col and cat_col:
        try:
            typo = analytics.emerging_typologies(dataset_id, t, time_col.name, cat_col)
            findings += findings_from_typology(typo)
        except Exception:
            pass

    try:
        mo = analytics.mo_signatures(dataset_id, t)
        findings += findings_from_mo(mo)
    except Exception:
        pass

    try:
        pred = _load_baked_predictions(dataset_id)
        findings += findings_from_predictions(pred)
    except Exception:
        pass

    selected = select(findings)
    return {
        "dataset_id": dataset_id,
        "generated_at": _utcnow_iso(),
        "findings": selected,
        "forecast": forecast,
        "backtest": backtest,
        "signals_used": sorted({f["type"] for f in selected}),
    }


def localize_findings(findings, language):
    """Translate each finding's user-facing title + suggested_action into `language`
    (data values inside — categories, area/person names, numbers — are preserved by
    the translator). One batched LLM call; no-op on 'en' or failure."""
    if language != "kn" or not findings:
        return findings
    from app.services import llm  # local import: llm is only needed for localization
    texts = []
    for f in findings:
        texts.append(f.get("title") or "")
        texts.append(f.get("suggested_action") or "")
    tr = llm.translate_batch(texts, language)
    for i, f in enumerate(findings):
        f["title"] = tr[2 * i] or f.get("title")
        f["suggested_action"] = tr[2 * i + 1] or f.get("suggested_action")
    return findings
