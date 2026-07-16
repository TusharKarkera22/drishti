"""Analytics implementations: grid hotspots, spike detection, anomaly
detection (IsolationForest), and per-area risk scoring with an optional
socio-demographic layer (per-capita rates, density/urbanization exposure)."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.core import store
from app.models.manifest import DatasetManifest, SemanticRole, TableSpec

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LNG = 111.320  # scaled by cos(lat) at runtime


def grid_hotspots(dataset_id: str, table: TableSpec, lat_col: str, lng_col: str,
                  category: str | None, hour_from: int | None, hour_to: int | None,
                  cell_km: float) -> dict:
    con = store.connect(dataset_id)
    try:
        time_col = table.first_by_role(SemanticRole.TIMESTAMP)
        cat_col = table.first_by_role(SemanticRole.CATEGORY)
        where, params = [f'"{lat_col}" IS NOT NULL', f'"{lng_col}" IS NOT NULL'], []
        if category and cat_col:
            where.append(f'"{cat_col.name}" = ?')
            params.append(category)
        if time_col and hour_from is not None and hour_to is not None:
            where.append(f'hour(TRY_CAST("{time_col.name}" AS TIMESTAMP)) BETWEEN ? AND ?')
            params.extend([hour_from, hour_to])

        mid_lat = con.execute(
            f'SELECT avg("{lat_col}") FROM "{table.name}" WHERE "{lat_col}" IS NOT NULL'
        ).fetchone()[0] or 13.0
        dlat = cell_km / KM_PER_DEG_LAT
        dlng = cell_km / (KM_PER_DEG_LNG * max(np.cos(np.radians(mid_lat)), 0.2))

        sql = f"""
            SELECT round("{lat_col}" / {dlat}) * {dlat} AS cell_lat,
                   round("{lng_col}" / {dlng}) * {dlng} AS cell_lng,
                   count(*) AS n
            FROM "{table.name}"
            WHERE {' AND '.join(where)}
            GROUP BY 1, 2
            HAVING count(*) >= 3
            ORDER BY n DESC
            LIMIT 2000
        """
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()

    counts = [r[2] for r in rows] or [1]
    p95 = float(np.percentile(counts, 95))
    return {
        "cell_km": cell_km,
        "cells": [
            {"lat": round(r[0], 5), "lng": round(r[1], 5), "count": r[2],
             "intensity": min(r[2] / p95, 1.0)}
            for r in rows
        ],
    }


def _daily_counts(dataset_id: str, table: str, time_col: str,
                  group_cols: list[str]) -> pd.DataFrame:
    con = store.connect(dataset_id)
    try:
        dims = "".join(f'"{c}", ' for c in group_cols)
        sql = f"""
            SELECT {dims}date_trunc('day', TRY_CAST("{time_col}" AS TIMESTAMP)) AS day,
                   count(*) AS n
            FROM "{table}" WHERE TRY_CAST("{time_col}" AS TIMESTAMP) IS NOT NULL
            GROUP BY ALL ORDER BY day
        """
        return con.execute(sql).df()
    finally:
        con.close()


def spike_alerts(dataset_id: str, table: TableSpec, time_col: str,
                 category_col: str | None, area_col: str | None,
                 window_days: int, z_threshold: float) -> dict:
    group_cols = [c for c in (area_col, category_col) if c]
    df = _daily_counts(dataset_id, table.name, time_col, group_cols)
    if df.empty:
        return {"alerts": []}
    df["day"] = pd.to_datetime(df["day"])
    end = df["day"].max()
    recent_start = end - pd.Timedelta(days=window_days)

    alerts = []
    grouped = df.groupby(group_cols) if group_cols else [((), df)]
    for key, g in grouped:
        base = g[g["day"] < recent_start]["n"]
        recent = g[g["day"] >= recent_start]["n"]
        if len(base) < 30 or recent.empty:
            continue
        mu, sigma = base.mean(), max(base.std(), 0.5)
        z = (recent.mean() - mu) / sigma
        if z >= z_threshold:
            key_t = key if isinstance(key, tuple) else (key,)
            alert = {
                "z_score": round(float(z), 2),
                "baseline_daily": round(float(mu), 2),
                "recent_daily": round(float(recent.mean()), 2),
                "pct_change": round(float((recent.mean() - mu) / mu * 100), 1) if mu else None,
                "window_days": window_days,
            }
            for col, val in zip(group_cols, key_t):
                alert[col] = val
            alerts.append(alert)
    alerts.sort(key=lambda a: -a["z_score"])
    return {"alerts": alerts[:50], "as_of": str(end.date())}


def detect_anomalies(dataset_id: str, table: TableSpec, contamination: float,
                     limit: int) -> dict:
    """IsolationForest over numeric + encoded categorical features; returns
    the records that deviate most from typical behavioral patterns."""
    con = store.connect(dataset_id)
    try:
        df = con.execute(f'SELECT * FROM "{table.name}" LIMIT 250000').df()
    finally:
        con.close()
    if df.empty:
        return {"anomalies": []}

    feats = pd.DataFrame(index=df.index)
    for col in table.columns:
        s = df[col.name]
        if col.semantic_role in (SemanticRole.MEASURE, SemanticRole.MONEY, SemanticRole.AGE):
            feats[col.name] = pd.to_numeric(s, errors="coerce").fillna(0)
        elif col.semantic_role in (SemanticRole.CATEGORY, SemanticRole.SUBCATEGORY,
                                   SemanticRole.ADMIN_AREA_1, SemanticRole.GENDER,
                                   SemanticRole.STATUS):
            freq = s.map(s.value_counts(normalize=True))
            feats[f"{col.name}_freq"] = freq.fillna(0)  # rarity as signal
        elif col.semantic_role == SemanticRole.TIMESTAMP:
            ts = pd.to_datetime(s, errors="coerce")
            feats["hour"] = ts.dt.hour.fillna(12)
            feats["dow"] = ts.dt.dayofweek.fillna(3)
    if feats.empty or feats.shape[1] < 2:
        return {"anomalies": [], "note": "not enough features for anomaly detection"}

    model = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
    scores = model.fit(feats).decision_function(feats)
    idx = np.argsort(scores)[:limit]

    id_col = table.first_by_role(SemanticRole.ID)
    out = []
    for i in idx:
        rec = df.iloc[int(i)]
        out.append({
            "record_id": str(rec[id_col.name]) if id_col else int(i),
            "score": round(float(-scores[int(i)]), 4),
            "record": {k: (str(v) if not pd.isna(v) else None) for k, v in rec.items()},
        })
    return {"anomalies": out, "contamination": contamination}


def load_demographics(dataset_id: str, manifest: DatasetManifest, area_col: str) -> dict[str, dict]:
    """Find a socio-demographic lookup table in the dataset: any non-primary
    table with an admin-area column plus a population-like measure. Returns
    {area_value: {population, density_per_km2, urbanization_pct, literacy_pct}}
    — empty dict when the dataset ships no demographics (everything degrades
    gracefully to pure volume-based scoring)."""
    for t in manifest.tables:
        if t.is_primary:
            continue
        join = next(
            (c for c in t.columns
             if c.semantic_role in (SemanticRole.ADMIN_AREA_1, SemanticRole.ADMIN_AREA_2)),
            None,
        )
        if not join:
            continue

        def col(pattern: str) -> str | None:
            for c in t.columns:
                if re.search(pattern, c.name.lower()):
                    return c.name
            return None

        pop = col(r"population|^pop($|_)")
        if not pop:
            continue
        dens, urb, lit = col(r"densit"), col(r"urban"), col(r"litera")
        con = store.connect(dataset_id)
        try:
            df = con.execute(f'SELECT * FROM "{t.name}"').df()
        finally:
            con.close()
        out = {}
        for _, r in df.iterrows():
            out[str(r[join.name])] = {
                "population": float(r[pop]),
                "density_per_km2": float(r[dens]) if dens else None,
                "urbanization_pct": float(r[urb]) if urb else None,
                "literacy_pct": float(r[lit]) if lit else None,
            }
        return out
    return {}


_BAND_MAP = [
    ("Night",     "00–05", 0,  5),
    ("Morning",   "06–11", 6, 11),
    ("Afternoon", "12–17", 12, 17),
    ("Evening",   "18–23", 18, 23),
]


def _hour_band_sql(time_col: str) -> str:
    """DuckDB CASE expression mapping an hour integer into a band label."""
    return (
        f"CASE "
        f"WHEN hour(TRY_CAST(\"{time_col}\" AS TIMESTAMP)) BETWEEN 0 AND 5 THEN 'Night' "
        f"WHEN hour(TRY_CAST(\"{time_col}\" AS TIMESTAMP)) BETWEEN 6 AND 11 THEN 'Morning' "
        f"WHEN hour(TRY_CAST(\"{time_col}\" AS TIMESTAMP)) BETWEEN 12 AND 17 THEN 'Afternoon' "
        f"ELSE 'Evening' "
        f"END"
    )


_BAND_HOURS = {b[0]: b[1] for b in _BAND_MAP}


def spatiotemporal_clusters(dataset_id: str, table: "TableSpec",
                            time_col: str | None, area_col: str | None,
                            cat_col: str | None,
                            *, min_share: float = 0.30,
                            min_n: int = 20) -> dict:
    """Group incidents by (category, area, hour-band); return cells where one
    band dominates (>= min_share) and has >= min_n cases — a genuine time
    concentration suitable for targeted patrol scheduling.

    Returns ``{"available": False, "reason": "..."}`` when required columns are
    absent; never raises.
    """
    if not time_col or not area_col or not cat_col:
        return {"available": False, "reason": "time_col / area_col / cat_col required"}

    band_expr = _hour_band_sql(time_col)
    con = store.connect(dataset_id)
    try:
        sql = f"""
            WITH base AS (
                SELECT "{cat_col}" AS category,
                       "{area_col}" AS area,
                       {band_expr} AS band,
                       count(*) AS n
                FROM "{table.name}"
                WHERE TRY_CAST("{time_col}" AS TIMESTAMP) IS NOT NULL
                  AND "{cat_col}" IS NOT NULL
                  AND "{area_col}" IS NOT NULL
                GROUP BY category, area, band
            ),
            totals AS (
                SELECT category, area, sum(n) AS total_n
                FROM base GROUP BY category, area
            ),
            ranked AS (
                SELECT b.category, b.area, b.band, b.n,
                       b.n * 1.0 / t.total_n AS share
                FROM base b JOIN totals t
                  ON b.category = t.category AND b.area = t.area
            ),
            best AS (
                SELECT category, area, band, n, share,
                       ROW_NUMBER() OVER (
                           PARTITION BY category, area ORDER BY n DESC
                       ) AS rn
                FROM ranked
            )
            SELECT category, area, band, n, share
            FROM best
            WHERE rn = 1 AND n >= {min_n} AND share >= {min_share}
            ORDER BY n DESC
            LIMIT 10
        """
        rows = con.execute(sql).fetchall()
    finally:
        con.close()

    clusters = [
        {
            "category": r[0], "area": r[1], "band": r[2],
            "band_hours": _BAND_HOURS.get(r[2], ""),
            "n": int(r[3]), "share": round(float(r[4]), 4),
        }
        for r in rows
    ]
    return {"available": True, "clusters": clusters}


def socioeconomic_correlation(dataset_id: str, manifest: "DatasetManifest",
                               area_col: str, *, min_areas: int = 5) -> dict:
    """Compute Pearson r between per-lakh crime rate and each socio-demographic
    factor (urbanization_pct, literacy_pct, density_per_km2) across areas that
    appear in both the primary table and the demographics lookup.

    Returns ``{"available": False, "reason": "..."}`` when demographics are
    absent or too few paired areas are found; never raises.
    """
    demo = load_demographics(dataset_id, manifest, area_col)
    if not demo:
        return {"available": False, "reason": "no demographics table in dataset"}

    # Per-area incident counts from primary table
    t = manifest.primary_table()
    con = store.connect(dataset_id)
    try:
        df_cnt = con.execute(
            f'SELECT "{area_col}" AS area, count(*) AS n FROM "{t.name}" '
            f'WHERE "{area_col}" IS NOT NULL GROUP BY area'
        ).df()
    finally:
        con.close()

    if df_cnt.empty:
        return {"available": False, "reason": "primary table is empty"}

    # Build a joined frame: area, count, population, factors
    records = []
    for _, row in df_cnt.iterrows():
        d = demo.get(str(row["area"]))
        if d and d.get("population") and d["population"] > 0:
            records.append({
                "area": row["area"],
                "count": int(row["n"]),
                "population": d["population"],
                "density_per_km2": d.get("density_per_km2"),
                "urbanization_pct": d.get("urbanization_pct"),
                "literacy_pct": d.get("literacy_pct"),
            })

    if len(records) < min_areas:
        return {
            "available": False,
            "reason": f"only {len(records)} paired areas (need {min_areas})",
            "n_areas": len(records),
        }

    joined = pd.DataFrame(records)
    joined["rate_per_lakh"] = joined["count"] / joined["population"] * 1e5

    factors = ["urbanization_pct", "literacy_pct", "density_per_km2"]
    correlations = []
    for factor in factors:
        sub = joined[["rate_per_lakh", factor]].dropna()
        if len(sub) < min_areas:
            continue
        x, y = sub["rate_per_lakh"].values, sub[factor].values
        if np.std(x) == 0 or np.std(y) == 0:
            continue
        r = float(np.corrcoef(x, y)[0, 1])
        correlations.append({
            "factor": factor,
            "r": round(r, 4),
            "n_areas": int(len(sub)),
            "direction": "positive" if r > 0 else ("negative" if r < 0 else "neutral"),
        })

    correlations.sort(key=lambda c: -abs(c["r"]))

    points = [
        {
            "area": str(rec["area"]),
            "rate_per_lakh": round(
                rec["count"] / rec["population"] * 1e5, 4
            ),
            "urbanization_pct": rec.get("urbanization_pct"),
            "literacy_pct": rec.get("literacy_pct"),
            "density_per_km2": rec.get("density_per_km2"),
        }
        for rec in records
    ]

    return {
        "available": True,
        "correlations": correlations,
        "n_areas": len(records),
        "points": points,
    }


def emerging_typologies(dataset_id: str, table: "TableSpec",
                         time_col: str | None, cat_col: str | None,
                         *, weeks: int = 8, min_per_week: float = 1.0) -> dict:
    """Detect crime categories whose weekly incident count is rising.

    Uses ``_daily_counts`` then resamples to weekly. Slope computed via
    ``np.polyfit``. Returns top 5 rising categories sorted by slope desc.
    Returns ``{"available": False, "reason": "..."}`` when columns are absent.
    """
    if not time_col or not cat_col:
        return {"available": False, "reason": "time_col / cat_col required"}

    df = _daily_counts(dataset_id, table.name, time_col, [cat_col])
    if df.empty:
        return {"available": False, "reason": "no data"}

    df["day"] = pd.to_datetime(df["day"])
    end = df["day"].max()
    start = end - pd.Timedelta(weeks=weeks)
    df = df[df["day"] >= start]
    if df.empty:
        return {"available": False, "reason": "insufficient recent data"}

    rising = []
    for cat, g in df.groupby(cat_col):
        weekly = (
            g.set_index("day")["n"]
            .resample("W").sum()
            .reindex(pd.date_range(start, end, freq="W"), fill_value=0)
        )
        if len(weekly) < 2:
            continue
        vals = weekly.values[-weeks:]
        recent_avg = float(vals.mean()) if len(vals) else 0.0
        if recent_avg < min_per_week:
            continue
        x = np.arange(len(vals))
        slope = float(np.polyfit(x, vals, 1)[0])
        if slope <= 0:
            continue
        mean = max(float(vals.mean()), 1.0)
        growth_pct = slope * len(vals) / mean * 100
        rising.append({
            "category": str(cat),
            "slope": round(slope, 4),
            "growth_pct": round(growth_pct, 1),
            "recent_weekly_avg": round(recent_avg, 2),
        })

    rising.sort(key=lambda r: -r["slope"])
    return {"available": True, "rising": rising[:5], "weeks": weeks}


def mo_signatures(dataset_id: str, table: "TableSpec",
                   *, min_cases: int = 8, min_areas: int = 2) -> dict:
    """Identify recurring method-of-operation signatures: (subtype, hour-band)
    pairs that appear across >= min_areas distinct areas with >= min_cases
    cases — evidence of a cross-jurisdiction recurring MO / possible single crew.

    Returns ``{"available": False, "reason": "..."}`` when required columns
    are absent; never raises.
    """
    time_spec = table.first_by_role(SemanticRole.TIMESTAMP) or table.first_by_role(SemanticRole.DATE)
    area_spec = table.first_by_role(SemanticRole.ADMIN_AREA_1)
    sub_spec = (table.first_by_role(SemanticRole.SUBCATEGORY)
                or table.first_by_role(SemanticRole.CATEGORY))
    id_spec = table.first_by_role(SemanticRole.ID)

    if not time_spec or not area_spec or not sub_spec:
        return {"available": False,
                "reason": "TIMESTAMP / ADMIN_AREA_1 / SUBCATEGORY (or CATEGORY) required"}

    time_col = time_spec.name
    area_col = area_spec.name
    sub_col = sub_spec.name
    band_expr = _hour_band_sql(time_col)
    id_expr = f'"{id_spec.name}"' if id_spec else "NULL"

    con = store.connect(dataset_id)
    try:
        sql = f"""
            WITH base AS (
                SELECT "{sub_col}" AS subtype,
                       {band_expr} AS band,
                       "{area_col}" AS area,
                       {id_expr} AS id
                FROM "{table.name}"
                WHERE TRY_CAST("{time_col}" AS TIMESTAMP) IS NOT NULL
                  AND "{sub_col}" IS NOT NULL
                  AND "{area_col}" IS NOT NULL
            ),
            agg AS (
                SELECT subtype, band,
                       count(*) AS n,
                       count(DISTINCT area) AS n_areas,
                       list(DISTINCT area) AS areas,
                       list(id) AS ids
                FROM base
                GROUP BY subtype, band
            )
            SELECT subtype, band, n, n_areas, areas, ids
            FROM agg
            WHERE n >= {min_cases} AND n_areas >= {min_areas}
            ORDER BY n DESC
            LIMIT 6
        """
        rows = con.execute(sql).fetchall()
    finally:
        con.close()

    sigs = []
    for r in rows:
        subtype, band, n, n_areas, areas, ids = r
        areas_list = list(areas)[:4] if areas else []
        example_ids = [str(i) for i in (ids or [])[:3]]
        sigs.append({
            "subtype": str(subtype),
            "band": str(band),
            "band_hours": _BAND_HOURS.get(str(band), ""),
            "n": int(n),
            "n_areas": int(n_areas),
            "areas": areas_list,
            "example_ids": example_ids,
        })

    return {"available": True, "signatures": sigs}


def _norm(v):
    """Min-max normalize to 0..1; constant (or empty) input -> all zeros."""
    v = np.nan_to_num(np.asarray(v, dtype=float))
    if v.size == 0:
        return v
    rng = v.max() - v.min()
    return (v - v.min()) / rng if rng else np.zeros_like(v)


def _risk_components(vols, slopes, zs, exposure, demo_used):
    """Per-area weighted contributions to the composite risk score, each on a
    0..1 scale, summing to the risk fraction. Without demographics there is no
    exposure term (weights 0.5/0.3/0.2); with it, 0.40/0.25/0.15/0.20.
    `exposure` must be pre-normalized to [0, 1] by the caller."""
    nv, ns, nz = _norm(vols), _norm(slopes), _norm(np.clip(np.asarray(zs, dtype=float), 0, None))
    if demo_used:
        return {"volume": 0.40 * nv, "trend": 0.25 * ns,
                "spike": 0.15 * nz, "exposure": 0.20 * np.asarray(exposure, dtype=float)}
    return {"volume": 0.5 * nv, "trend": 0.3 * ns, "spike": 0.2 * nz, "exposure": np.zeros_like(nv)}


def area_risk(dataset_id: str, table: TableSpec, time_col: str, area_col: str,
              horizon_days: int, demographics: dict[str, dict] | None = None) -> dict:
    df = _daily_counts(dataset_id, table.name, time_col, [area_col])
    if df.empty:
        return {"areas": []}
    df["day"] = pd.to_datetime(df["day"])
    end = df["day"].max()
    demographics = demographics or {}

    areas = []
    for area, g in df.groupby(area_col):
        g = g.set_index("day")["n"].asfreq("D", fill_value=0)
        if len(g) < 14:
            continue
        recent = g[-28:]
        volume = float(recent.mean())
        x = np.arange(len(recent))
        slope = float(np.polyfit(x, recent.values, 1)[0]) if len(recent) > 1 else 0.0
        base = g[:-28]
        z = float((recent[-7:].mean() - base.mean()) / max(base.std(), 0.5)) if len(base) > 30 else 0.0
        forecast = max(volume + slope * (len(recent) + horizon_days / 2), 0)
        row = {
            "area": area,
            "recent_daily_avg": round(volume, 2),
            "trend_slope": round(slope, 4),
            "spike_z": round(z, 2),
            "forecast_daily": round(forecast, 2),
        }
        demo = demographics.get(str(area))
        if demo and demo.get("population"):
            row["population"] = demo["population"]
            row["per_lakh_daily"] = round(volume / demo["population"] * 100000, 3)
            row["density_per_km2"] = demo.get("density_per_km2")
            row["urbanization_pct"] = demo.get("urbanization_pct")
        areas.append(row)

    demo_used = sum(1 for a in areas if "per_lakh_daily" in a) >= max(len(areas) // 2, 1)
    if areas:
        vols = np.array([a["recent_daily_avg"] for a in areas])
        slopes = np.array([a["trend_slope"] for a in areas])
        zs = np.array([a["spike_z"] for a in areas])
        exposure = np.zeros(len(areas))
        if demo_used:
            # Socio-demographic exposure: dense, urbanized areas concentrate
            # opportunity and repeat victimization. Weights in docs/architecture.md.
            dens = np.array([a.get("density_per_km2") or np.nan for a in areas])
            urb = np.array([a.get("urbanization_pct") or np.nan for a in areas])
            exposure = 0.6 * _norm(dens) + 0.4 * _norm(urb)
            for a, e in zip(areas, exposure):
                a["exposure_factor"] = round(float(e), 3)

        comp = _risk_components(vols, slopes, zs, exposure, demo_used)
        risk = comp["volume"] + comp["trend"] + comp["spike"] + comp["exposure"]
        for i, a in enumerate(areas):
            a["components"] = {k: round(float(comp[k][i]), 3) for k in ("volume", "trend", "spike", "exposure")}
            a["risk_score"] = round(float(risk[i]) * 100, 1)
        areas.sort(key=lambda a: -a["risk_score"])
    return {"areas": areas, "horizon_days": horizon_days, "as_of": str(end.date()),
            "demographics_used": bool(demo_used)}
