import numpy as np
import pandas as pd

from app.services.analytics import _norm, _risk_components


def test_norm_constant_series_is_zero():
    assert np.allclose(_norm([5, 5, 5]), [0, 0, 0])


def test_norm_scales_to_unit_range():
    assert np.allclose(_norm([0, 5, 10]), [0.0, 0.5, 1.0])


def test_risk_components_no_demo_has_zero_exposure_and_sums_to_one_at_max():
    comp = _risk_components([0, 10], [0, 1], [0, 2], np.zeros(2), demo_used=False)
    assert np.allclose(comp["exposure"], [0.0, 0.0])
    # the max area maxes every normalized component -> 0.5 + 0.3 + 0.2 = 1.0
    total = comp["volume"] + comp["trend"] + comp["spike"] + comp["exposure"]
    assert round(float(total[1]), 3) == 1.0


def test_risk_components_demo_weights_include_exposure():
    comp = _risk_components([0, 10], [0, 1], [0, 2], np.array([0.0, 1.0]), demo_used=True)
    assert round(float(comp["exposure"][1]), 3) == 0.20
    total = comp["volume"] + comp["trend"] + comp["spike"] + comp["exposure"]
    assert round(float(total[1]), 3) == 1.0  # 0.40+0.25+0.15+0.20


from app.services import insights as ins


def test_severity_is_bounded_and_monotonic():
    assert ins.sev_spike(2.5) == 40 and ins.sev_spike(6.0) > ins.sev_spike(3.0)
    assert 0 <= ins.sev_spike(100) <= 100
    assert ins.sev_risk(78.4) == 78
    assert ins.sev_data_gap(0.0) <= ins.sev_data_gap(0.5) <= 80


def test_findings_from_spikes_shapes_a_finding():
    alerts = [{"z_score": 3.1, "baseline_daily": 1.0, "recent_daily": 3.4,
               "pct_change": 240.0, "district": "Bengaluru City", "crime_group": "Cybercrime"}]
    out = ins.findings_from_spikes(alerts, area_col="district", cat_col="crime_group", z_threshold=2.0)
    assert len(out) == 1
    f = out[0]
    assert f["type"] == "spike" and f["area"] == "Bengaluru City" and f["category"] == "Cybercrime"
    assert "Cybercrime" in f["title"] and f["drill"]["surface"] == "dashboard"
    assert f["suggested_action"]


def test_findings_from_risk_only_rising_areas():
    areas = [{"area": "Mysuru", "risk_score": 78.0, "trend_slope": 0.4, "forecast_daily": 12.0,
              "recent_daily_avg": 9.0},
             {"area": "Calm", "risk_score": 5.0, "trend_slope": -0.2, "forecast_daily": 1.0,
              "recent_daily_avg": 1.0}]
    out = ins.findings_from_risk(areas, top=3)
    assert [f["area"] for f in out] == ["Mysuru"]
    assert out[0]["type"] == "rising_risk" and out[0]["drill"]["surface"] == "map"


def test_findings_from_network_uses_repeat_offenders():
    summ = {"repeat_offenders": [{"node": "accused:P42", "label": "P. Kumar", "case_count": 9}]}
    out = ins.findings_from_network(summ, top=3)
    assert out[0]["type"] == "network_hub" and "9" in out[0]["title"]
    assert out[0]["drill"] == {"surface": "network", "params": {"node": "accused:P42"}}


def test_findings_from_anomalies_collapses_to_one_batch():
    anom = {"anomalies": [{"record_id": "FIR1", "score": 0.7}, {"record_id": "FIR2", "score": 0.6}]}
    out = ins.findings_from_anomalies(anom)
    assert len(out) == 1 and out[0]["type"] == "anomaly" and out[0]["evidence"]["count"] == 2


def test_findings_from_data_gaps_picks_worst_column():
    digest = {"columns": [
        {"name": "accused_phone", "null_pct": 0.0, "phone_like_rate": 0.6},
        {"name": "property_loss", "null_pct": 0.18},
        {"name": "clean", "null_pct": 0.0}]}
    out = ins.findings_from_data_gaps(digest)
    assert len(out) == 1 and out[0]["type"] == "data_gap"
    assert out[0]["evidence"]["column"] == "accused_phone"  # worst gap wins
    assert out[0]["drill"]["surface"] == "intake"


def test_finding_builders_tolerate_none_input():
    # build_insights guards most call sites, but the builders must degrade, not crash
    assert ins.findings_from_risk(None) == []
    assert ins.findings_from_network(None) == []
    assert ins.findings_from_anomalies(None) == []
    assert ins.findings_from_data_gaps(None) == []


def test_select_caps_per_type_and_keeps_headline():
    findings = (
        [{"id": f"spike:{i}", "type": "spike", "severity": 90 - i} for i in range(5)] +
        [{"id": "risk:0", "type": "rising_risk", "severity": 30}]
    )
    out = ins.select(findings, per_type_cap=3, top=7)
    assert sum(1 for f in out if f["type"] == "spike") == 3
    # the low-severity rising_risk headline is still retained
    assert any(f["id"] == "risk:0" for f in out)


def _synthetic_daily(days=200, hot="A"):
    """One area gets all the volume so the top-k must capture ~100%."""
    base = pd.Timestamp("2025-01-01")
    rows = []
    for d in range(days):
        day = base + pd.Timedelta(days=d)
        for area in ["A", "B", "C", "D", "E", "F"]:
            rows.append({"area": area, "day": day, "n": 20 if area == hot else 1})
    return pd.DataFrame(rows)


def test_capture_at_k_flags_the_hot_area():
    res = ins.capture_at_k(_synthetic_daily(), area_col="area")
    assert res["available"] is True
    assert res["capture_rate"] >= 0.7  # the dominant area is reliably in top-k
    assert res["k"] >= 3 and res["folds"] >= 1


def test_capture_at_k_guards_short_history():
    res = ins.capture_at_k(_synthetic_daily(days=20), area_col="area")
    assert res["available"] is False and "history" in res["reason"]


def test_confidence_thresholds():
    assert ins.confidence(200, 6) == "high"
    assert ins.confidence(90, 6) == "medium"
    assert ins.confidence(10, 6) == "low"


_SAMPLE_INSIGHTS = {
    "findings": [
        {"type": "spike", "severity": 88, "title": "Cybercrime in Bengaluru City up 240%", "area": "Bengaluru City"},
        {"type": "rising_risk", "severity": 78, "title": "Mysuru trending up", "area": "Mysuru"},
        {"type": "data_gap", "severity": 41, "title": "18% of accused_phone is malformed", "area": None},
    ],
    "forecast": {"areas": [{"area": "Mysuru", "forecast_daily": 12.0, "risk_score": 78.0}]},
    "backtest": {"available": True, "capture_rate": 0.66},
}


def test_commander_brief_uses_injected_llm():
    res = ins.commander_brief(_SAMPLE_INSIGHTS, language="en", llm_fn=lambda messages: "LIVE BRIEF.")
    assert res == {"brief": "LIVE BRIEF.", "language": "en", "source": "llm"}


def test_commander_brief_falls_back_when_llm_raises():
    def boom(messages):
        raise RuntimeError("llm down")
    res = ins.commander_brief(_SAMPLE_INSIGHTS, language="en", llm_fn=boom)
    assert res["source"] == "fallback" and res["brief"]
    assert "Cybercrime" in res["brief"]  # leads with the most urgent finding


def test_commander_brief_no_llm_is_fallback():
    res = ins.commander_brief(_SAMPLE_INSIGHTS, language="en", llm_fn=None)
    assert res["source"] == "fallback" and "66%" in res["brief"]
