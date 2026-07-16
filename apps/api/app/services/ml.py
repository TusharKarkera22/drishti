"""Predictive-Intelligence layer: supervised models trained OFFLINE
(``scripts/train_models.py``), serialised with joblib, and loaded + scored
here at request time (never trained on the request path — see
``routers/predict.py``).

Two models per dataset, both degrading gracefully to ``{"available": False,
"reason": ...}`` rather than raising when the dataset lacks the needed roles
or labelled history:

  - detection: will an OPEN case eventually be solved? (HistGradientBoosting-
    Classifier over closed cases, label = detected/undetected from STATUS)
  - duration: how many days until resolution? (HistGradientBoostingRegressor,
    only available when the dataset ships a resolution-date table — e.g.
    ksp-fir's ChargesheetDetails.csdate; ksp-crime has no such table)

GOVERNANCE (non-negotiable, see docs/superpowers/plans/2026-06-30-predictive-
triage.md): features are CASE-LEVEL ONLY — crime type, gravity, area, hour/
day-of-week, reporting delay, property loss, and accused count. This module
must NEVER read caste, religion, or any person's name/identity/demographic
column as a model feature. This is a case-triage model, not an individual
risk score; every consumer must show "advisory — human review required."
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import train_test_split

from app.core import store
from app.models.manifest import DatasetManifest, SemanticRole, TableSpec

MIN_TRAIN_ROWS = 200

# Status-value fragments (case-insensitive substring match). Verified against
# real values — ksp-crime: {Chargesheeted, Convicted, Acquitted,
# Closed - Undetected, Under Investigation}; ksp-fir: {Charge Sheeted,
# Convicted, Acquitted, Closed, Under Investigation}.
_DETECTED_FRAGMENTS = ("charge", "convict", "acquit")
_UNDETECTED_FRAGMENTS = ("undetected", "closed")
_OPEN_FRAGMENTS = ("investigation", "pending", "open")

_DURATION_TABLE_PATTERN = re.compile(r"csdate|chargesheet|disposal|closed", re.IGNORECASE)


def _detected_labels(status: str) -> bool:
    s = (status or "").lower()
    return any(frag in s for frag in _DETECTED_FRAGMENTS)


def _undetected_labels(status: str) -> bool:
    s = (status or "").lower()
    return any(frag in s for frag in _UNDETECTED_FRAGMENTS)


def _is_open_status(status: str) -> bool:
    s = (status or "").lower()
    return any(frag in s for frag in _OPEN_FRAGMENTS)


def _n_accused_by_case(dataset_id: str, manifest: DatasetManifest,
                       primary: TableSpec, id_col: str) -> dict:
    """Best-effort per-case accused count: find a child table with a
    PERSON_NAME role linked to the primary via manifest.relations, COUNT rows
    per joined id. Returns {} (caller defaults to 0) if no clean join resolves
    — n_accused is a nice-to-have feature, never a hard requirement.

    KNOWN LEAKAGE RISK: on the synthetic ksp-crime seed data, accused rows are
    ONLY ever generated for cases whose status is already Chargesheeted/
    Convicted/Acquitted (see scripts/generate_data.py's `solved_mask`), so
    n_accused > 0 is a deterministic proxy for the detection label there,
    not a genuine leading indicator — training on it there yields a
    misleadingly perfect AUC (observed ~1.0; ~0.50 with the feature dropped).
    Real-world data is unlikely to be this clean-cut, but any consumer of
    `importances` should treat a near-total weight on n_accused as a signal
    to inspect the underlying data-generation process, not a cause for
    celebration. Kept as a feature (per spec) rather than dropped, since a
    genuinely predictive n_accused is exactly the kind of soft signal this
    model should exploit on real data."""
    for rel in manifest.relations:
        if rel.to_table != primary.name:
            continue
        child = manifest.table(rel.from_table)
        if not child or not child.first_by_role(SemanticRole.PERSON_NAME):
            continue
        if rel.to_column != id_col:
            continue
        con = store.connect(dataset_id)
        try:
            sql = (
                f'SELECT "{rel.from_column}" AS join_id, count(*) AS n '
                f'FROM "{rel.from_table}" '
                f'WHERE "{rel.from_column}" IS NOT NULL '
                f'GROUP BY "{rel.from_column}"'
            )
            df = con.execute(sql).df()
        except Exception:
            continue
        finally:
            con.close()
        return dict(zip(df["join_id"].astype(str), df["n"].astype(int)))
    return {}


def build_features(dataset_id: str, manifest: DatasetManifest, for_training: bool
                    ) -> tuple[pd.DataFrame, "pd.Series | None", list]:
    """Pull case-level features from the primary table via store.connect().

    for_training=True  -> rows are the CLOSED cases (status matches detected or
                           undetected), y = 1/0.
    for_training=False -> rows are the OPEN cases (status matches "investigation"
                          /"pending"/"open"), y = None (nothing to score against).

    Columns are resolved by SEMANTIC ROLE, never hardcoded names. Only columns
    whose role actually exists in this dataset are included — see the module
    docstring's governance note for what may never appear here.
    """
    t = manifest.primary_table()
    status_col = t.first_by_role(SemanticRole.STATUS)
    if not status_col:
        return pd.DataFrame(), None, []

    id_col = t.first_by_role(SemanticRole.ID)
    cat_col = t.first_by_role(SemanticRole.CATEGORY)
    area_col = t.first_by_role(SemanticRole.ADMIN_AREA_1)
    time_col = t.first_by_role(SemanticRole.TIMESTAMP)
    money_col = t.first_by_role(SemanticRole.MONEY)
    gravity_col = next((c for c in t.columns if c.name == "gravity"), None)
    # a second TIMESTAMP-role column (besides the primary occurrence one) acts as
    # "reported"; find one whose name hints at reporting/registration.
    all_ts = [c for c in t.columns if c.semantic_role == SemanticRole.TIMESTAMP]
    reported_col = None
    if time_col and len(all_ts) > 1:
        reported_col = next(
            (c for c in all_ts if c.name != time_col.name
             and re.search(r"report|regist|info", c.name, re.IGNORECASE)),
            None,
        )

    select_cols = {status_col.name: "status"}
    if id_col:
        select_cols[id_col.name] = "case_ref_id"
    if cat_col:
        select_cols[cat_col.name] = "crime_type"
    if area_col:
        select_cols[area_col.name] = "area"
    if gravity_col:
        select_cols[gravity_col.name] = "gravity"
    if time_col:
        select_cols[time_col.name] = "occurrence_ts"
    if reported_col:
        select_cols[reported_col.name] = "reported_ts_raw"
    if money_col:
        select_cols[money_col.name] = "property_loss"

    sql_cols = ", ".join(f'"{raw}" AS "{alias}"' for raw, alias in select_cols.items())
    con = store.connect(dataset_id)
    try:
        df = con.execute(f'SELECT {sql_cols} FROM "{t.name}"').df()
    finally:
        con.close()

    if for_training:
        mask = df["status"].apply(lambda s: _detected_labels(s) or _undetected_labels(s))
        df = df[mask].copy()
        y = df["status"].apply(lambda s: 1 if _detected_labels(s) else 0).reset_index(drop=True)
    else:
        mask = df["status"].apply(_is_open_status)
        df = df[mask].copy()
        y = None

    ids = (df["case_ref_id"].astype(str).tolist() if "case_ref_id" in df.columns
           else [str(i) for i in df.index])

    feats = pd.DataFrame(index=range(len(df)))
    if "crime_type" in df.columns:
        feats["crime_type"] = pd.Categorical(df["crime_type"].reset_index(drop=True))
    if "gravity" in df.columns:
        feats["gravity"] = pd.Categorical(df["gravity"].reset_index(drop=True))
    if "area" in df.columns:
        feats["area"] = pd.Categorical(df["area"].reset_index(drop=True))
    if "occurrence_ts" in df.columns:
        ts = pd.to_datetime(df["occurrence_ts"], errors="coerce").reset_index(drop=True)
        feats["hour"] = ts.dt.hour.fillna(-1).astype(int)
        feats["dow"] = ts.dt.dayofweek.fillna(-1).astype(int)
        if "reported_ts_raw" in df.columns:
            rep = pd.to_datetime(df["reported_ts_raw"], errors="coerce").reset_index(drop=True)
            delay_h = (rep - ts).dt.total_seconds() / 3600.0
            feats["report_delay_h"] = delay_h.clip(lower=0).fillna(delay_h.median() or 0)
    if "property_loss" in df.columns:
        feats["property_loss"] = pd.to_numeric(
            df["property_loss"].reset_index(drop=True), errors="coerce").fillna(0.0)

    if id_col:
        n_acc = _n_accused_by_case(dataset_id, manifest, t, id_col.name)
        feats["n_accused"] = [n_acc.get(str(i), 0) for i in ids] if n_acc else 0
    else:
        feats["n_accused"] = 0

    feats = feats.reset_index(drop=True)
    return feats, y, ids


def _categorical_columns(X: pd.DataFrame) -> list[str]:
    return [c for c in X.columns if isinstance(X[c].dtype, pd.CategoricalDtype)]


def _fillna_mixed(X: pd.DataFrame) -> pd.DataFrame:
    """fillna across a frame that mixes pandas `category` columns (filled with
    an explicit "__missing__" category) and numeric columns (filled with 0).
    A blind `X.fillna(0)` raises on categorical columns because 0 isn't one of
    their categories."""
    X = X.copy()
    for c in _categorical_columns(X):
        if "__missing__" not in X[c].cat.categories:
            X[c] = X[c].cat.add_categories(["__missing__"])
        X[c] = X[c].fillna("__missing__")
    num_cols = [c for c in X.columns if c not in _categorical_columns(X)]
    X[num_cols] = X[num_cols].fillna(0)
    return X


def _align_categories_for_predict(X: pd.DataFrame, cat_cols: list[str]) -> pd.DataFrame:
    """Coerce `cat_cols` to pandas `category` dtype for a prediction-time frame
    (values may not already be Categorical — e.g. OPEN cases can show a crime
    type never seen among CLOSED training cases) and fillna the rest with 0.
    Unseen-category values simply become their own new category in this fresh
    Categorical — HistGradientBoosting only needs consistent category CODES
    within a single predict() call, not identical categories to training."""
    X = X.copy()
    for c in cat_cols:
        if c in X.columns:
            if not isinstance(X[c].dtype, pd.CategoricalDtype):
                X[c] = pd.Categorical(X[c])
            if "__missing__" not in X[c].cat.categories:
                X[c] = X[c].cat.add_categories(["__missing__"])
            X[c] = X[c].fillna("__missing__")
    num_cols = [c for c in X.columns if c not in cat_cols]
    X[num_cols] = X[num_cols].fillna(0)
    return X


def train_detection(dataset_id: str) -> dict:
    """Train HistGradientBoostingClassifier on closed cases; returns
    {"available": False, "reason": ...} when there are <MIN_TRAIN_ROWS
    labelled rows or only one class present — never raises."""
    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        return {"available": False, "reason": f"no manifest for dataset '{dataset_id}'"}

    X, y, ids = build_features(dataset_id, manifest, for_training=True)
    if X.empty or y is None:
        return {"available": False, "reason": "no STATUS column on the primary table"}
    if len(X) < MIN_TRAIN_ROWS:
        return {"available": False,
                "reason": f"only {len(X)} labelled rows (need >= {MIN_TRAIN_ROWS})"}
    if y.nunique() < 2:
        return {"available": False, "reason": "only one label class present (no undetected cases)"}

    cat_cols = _categorical_columns(X)
    X = _fillna_mixed(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42,
        stratify=y if y.nunique() > 1 else None,
    )

    model = HistGradientBoostingClassifier(
        categorical_features="from_dtype", random_state=42,
    )
    model.fit(X_train, y_train)

    auc = None
    try:
        proba = model.predict_proba(X_test)[:, 1]
        if y_test.nunique() > 1:
            auc = float(roc_auc_score(y_test, proba))
    except Exception:
        auc = None

    try:
        imp = permutation_importance(model, X_test, y_test, n_repeats=5, random_state=42)
        importances = {col: round(float(v), 4) for col, v in zip(X.columns, imp.importances_mean)}
    except Exception:
        importances = {}

    return {
        "available": True,
        "model": model,
        "features": list(X.columns),
        "categorical_features": cat_cols,
        "importances": importances,
        "base_rate": round(float(y.mean()), 4),
        "n_train": int(len(X)),
        "auc": round(auc, 4) if auc is not None else None,
    }


def _find_duration_table(manifest: DatasetManifest, primary: TableSpec):
    """Find a manifest table (not the primary) with a DATE/TIMESTAMP column
    whose name matches csdate|chargesheet|disposal|closed, joined to the
    primary via manifest.relations. Returns (table, date_col_name,
    from_column) or None when no such table/relation exists (e.g. ksp-crime,
    which has no resolution-date table at all).

    The relation doesn't have to point directly at the primary table's own
    name: many analytics views (e.g. ksp-fir's case_master_analytics) are
    themselves derived from an upstream "case master" table that the raw
    manifest.relations still reference (e.g. ChargesheetDetails -> CaseMaster,
    not -> case_master_analytics). We also accept a relation whose to_table
    exposes an ID-role column on `rel.to_column` — i.e. the FK plainly targets
    *a* case identifier, even if it's not literally the primary's table name.
    The actual join is then done by VALUE against the primary's own ID column
    (see train_duration), which is safe because in that pattern the primary
    analytics view's id column is sourced 1:1 from that same upstream case id
    (verified for ksp-fir: case_master_analytics.case_id <- CaseMaster."CaseMasterID").
    """
    id_col = primary.first_by_role(SemanticRole.ID)
    for t in manifest.tables:
        if t.name == primary.name:
            continue
        date_col = next(
            (c for c in t.columns
             if c.semantic_role in (SemanticRole.TIMESTAMP, SemanticRole.DATE)
             and _DURATION_TABLE_PATTERN.search(c.name)),
            None,
        )
        if not date_col:
            continue
        rel = next(
            (r for r in manifest.relations if r.from_table == t.name
             and (r.to_table == primary.name or _points_at_an_id(manifest, r))),
            None,
        )
        if not rel:
            continue
        return t, date_col.name, rel.from_column
    return None


def _points_at_an_id(manifest: DatasetManifest, rel) -> bool:
    """True when a relation's target column is itself ID-role — i.e. the FK
    plainly targets *some* case/entity identifier, even if manifest.relations
    was recorded against an upstream raw table rather than a derived primary
    analytics view built 1:1 from it (see _find_duration_table docstring)."""
    target = manifest.table(rel.to_table)
    if not target:
        return False
    col = next((c for c in target.columns if c.name == rel.to_column), None)
    return bool(col and col.semantic_role == SemanticRole.ID)


def train_duration(dataset_id: str) -> dict:
    """Train HistGradientBoostingRegressor to predict days-to-resolution.
    Target = days between the primary's occurrence timestamp and the
    resolution date found by _find_duration_table(). Returns
    {"available": False, "reason": ...} when no such table/relation/timestamp
    resolves (this is the expected, graceful outcome for ksp-crime)."""
    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        return {"available": False, "reason": f"no manifest for dataset '{dataset_id}'"}

    t = manifest.primary_table()
    if not t:
        return {"available": False, "reason": "dataset has no tables"}
    id_col = t.first_by_role(SemanticRole.ID)
    time_col = t.first_by_role(SemanticRole.TIMESTAMP)
    if not id_col or not time_col:
        return {"available": False, "reason": "primary table needs ID + TIMESTAMP roles"}

    found = _find_duration_table(manifest, t)
    if not found:
        return {"available": False,
                "reason": "no resolution-date table (csdate/chargesheet/disposal/closed) "
                          "joined to the primary via manifest.relations"}
    dur_table, date_col, from_col = found

    X, y, ids = build_features(dataset_id, manifest, for_training=True)
    if X.empty:
        return {"available": False, "reason": "no closed cases to train on"}

    con = store.connect(dataset_id)
    try:
        res_df = con.execute(
            f'SELECT "{from_col}" AS join_id, min(TRY_CAST("{date_col}" AS TIMESTAMP)) AS res_date '
            f'FROM "{dur_table.name}" WHERE "{date_col}" IS NOT NULL GROUP BY "{from_col}"'
        ).df()
        occ_df = con.execute(
            f'SELECT "{id_col.name}" AS join_id, TRY_CAST("{time_col.name}" AS TIMESTAMP) AS occ_date '
            f'FROM "{t.name}"'
        ).df()
    finally:
        con.close()

    res_df["join_id"] = res_df["join_id"].astype(str)
    occ_df["join_id"] = occ_df["join_id"].astype(str)
    joined = res_df.merge(occ_df, on="join_id", how="inner")
    joined["days"] = (pd.to_datetime(joined["res_date"]) - pd.to_datetime(joined["occ_date"])
                       ).dt.total_seconds() / 86400.0
    joined = joined[(joined["days"] >= 0) & joined["days"].notna()]
    if len(joined) < MIN_TRAIN_ROWS:
        return {"available": False,
                "reason": f"only {len(joined)} resolved-duration rows (need >= {MIN_TRAIN_ROWS})"}

    ids_df = pd.DataFrame({"case_ref_id": ids})
    ids_df["join_id"] = ids_df["case_ref_id"].astype(str)
    days_by_id = dict(zip(joined["join_id"], joined["days"]))
    target = ids_df["join_id"].map(days_by_id)

    keep = target.notna()
    X_dur = X[keep.values].reset_index(drop=True)
    y_dur = target[keep].reset_index(drop=True).astype(float)
    if len(X_dur) < MIN_TRAIN_ROWS:
        return {"available": False,
                "reason": f"only {len(X_dur)} feature rows have a resolved duration "
                          f"(need >= {MIN_TRAIN_ROWS})"}

    cat_cols = _categorical_columns(X_dur)
    X_dur = _fillna_mixed(X_dur)

    X_train, X_test, y_train, y_test = train_test_split(
        X_dur, y_dur, test_size=0.25, random_state=42,
    )
    model = HistGradientBoostingRegressor(
        categorical_features="from_dtype", random_state=42,
    )
    model.fit(X_train, y_train)
    mae = float(mean_absolute_error(y_test, model.predict(X_test))) if len(X_test) else None

    return {
        "available": True,
        "model": model,
        "features": list(X_dur.columns),
        "categorical_features": cat_cols,
        "median_days": round(float(y_dur.median()), 1),
        "p90_days": round(float(y_dur.quantile(0.90)), 1),
        "mae": round(mae, 2) if mae is not None else None,
        "n_train": int(len(X_dur)),
    }


def _top_factors(row: pd.Series, importances: dict, base_means: dict, top_n: int = 3) -> list[str]:
    """Lightweight, honest explanation: rank this case's features by their
    global importance, then describe whether each notable feature sits above
    or below the training-set average — no SHAP dependency (see plan notes:
    the production upgrade path is SHAP)."""
    ranked = sorted(importances.items(), key=lambda kv: -kv[1])[:top_n]
    out = []
    for feat, _weight in ranked:
        if feat not in row.index:
            continue
        val = row[feat]
        base = base_means.get(feat)
        if isinstance(val, (int, float, np.integer, np.floating)) and base is not None:
            if val > base * 1.15:
                out.append(f"{feat} above average ({val:.1f} vs {base:.1f})")
            elif val < base * 0.85:
                out.append(f"{feat} below average ({val:.1f} vs {base:.1f})")
            else:
                out.append(f"{feat} near average")
        else:
            out.append(f"{feat}: {val}")
    return out or ["no standout factors vs. the training base rate"]


def predict_open(dataset_id: str, det_bundle: dict, dur_bundle: dict, limit: int = 25) -> dict:
    """Score the OPEN cases with the (already-trained/loaded) bundles.
    Never trains — det_bundle/dur_bundle are the dicts returned by
    train_detection()/train_duration() (or loaded from a joblib bake).
    Returns {"available": False, "reason": ...} when detection is unavailable
    (duration is optional — ksp-crime has none)."""
    if not det_bundle or not det_bundle.get("available"):
        return {"available": False,
                "reason": (det_bundle or {}).get("reason", "no detection model available")}

    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        return {"available": False, "reason": f"no manifest for dataset '{dataset_id}'"}

    X, _, ids = build_features(dataset_id, manifest, for_training=False)
    if X.empty:
        return {"available": True, "flagged": [], "by_area": [],
                "meta": {"n_open": 0, "reason": "no open cases"}}

    model = det_bundle["model"]
    feat_cols = det_bundle["features"]
    cat_cols = det_bundle.get("categorical_features", [])
    for col in feat_cols:
        if col not in X.columns:
            X[col] = 0
    X = X[feat_cols]
    X_num = _align_categories_for_predict(X, cat_cols)

    probs = model.predict_proba(X_num)[:, 1]

    dur_model = None
    median_days = None
    if dur_bundle and dur_bundle.get("available"):
        dur_model = dur_bundle["model"]
        dur_feat_cols = dur_bundle["features"]
        dur_cat_cols = dur_bundle.get("categorical_features", [])
        median_days = dur_bundle.get("median_days")
        X_dur = X.copy()
        for col in dur_feat_cols:
            if col not in X_dur.columns:
                X_dur[col] = 0
        X_dur = X_dur[dur_feat_cols]
        X_dur = _align_categories_for_predict(X_dur, dur_cat_cols)
        predicted_days = dur_model.predict(X_dur)
    else:
        predicted_days = [None] * len(X_num)

    importances = det_bundle.get("importances", {})
    base_means = {}
    for col in feat_cols:
        if col in X_num.columns and pd.api.types.is_numeric_dtype(X_num[col]):
            base_means[col] = float(X_num[col].mean())

    flagged = []
    for i in range(len(X_num)):
        prob = float(probs[i])
        pdays = predicted_days[i]
        stall = bool(median_days is not None and pdays is not None and pdays > median_days)
        flagged.append({
            "id": ids[i] if i < len(ids) else str(i),
            "detection_prob": round(prob, 4),
            "predicted_days": round(float(pdays), 1) if pdays is not None else None,
            "stall": stall,
            "factors": _top_factors(X_num.iloc[i], importances, base_means),
        })

    flagged.sort(key=lambda f: f["detection_prob"])
    flagged = flagged[:limit]

    area_col = "area" if "area" in X.columns else None
    by_area = []
    if area_col:
        area_series = X[area_col].astype(str)
        area_df = pd.DataFrame({"area": area_series, "prob": probs})
        for area, g in area_df.groupby("area"):
            by_area.append({
                "area": area,
                "predicted_detection_rate": round(float(g["prob"].mean()), 4),
                "n_open": int(len(g)),
            })
        by_area.sort(key=lambda a: a["predicted_detection_rate"])

    # Build meta dict with optional keys from bundles
    meta = {
        "n_open": int(len(X_num)),
        "n_flagged": len(flagged),
    }
    if det_bundle.get("auc") is not None:
        meta["detection_auc"] = det_bundle["auc"]
    if det_bundle.get("base_rate") is not None:
        meta["base_rate"] = det_bundle["base_rate"]
    meta["has_duration"] = bool(dur_model is not None)

    return {
        "available": True,
        "flagged": flagged,
        "by_area": by_area,
        "meta": meta,
    }
