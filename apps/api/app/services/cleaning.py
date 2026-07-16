"""Deterministic data cleaners for the Intake pipeline. Each cleaner takes a DataFrame
and a target column (plus params) and returns a CleanResult: the cleaned frame, an
audit of every change, stats, warnings, and quarantined rows (never dropped silently)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from rapidfuzz import fuzz, process


@dataclass
class Change:
    column: str
    row_key: str
    op: str
    before: Any
    after: Any


@dataclass
class CleanResult:
    df: pd.DataFrame
    changes: list[Change] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    quarantined: list[dict] = field(default_factory=list)


def _key(df: pd.DataFrame, i: int, key_col: str | None) -> str:
    return str(df[key_col].iloc[i]) if key_col else str(i)


# ---- Stage 1: format normalization ----

def normalize_dates(df: pd.DataFrame, column: str, *, dayfirst: bool = True,
                    key_col: str | None = None) -> CleanResult:
    out = df.copy()
    # format='mixed' handles columns with multiple date formats (e.g. DD/MM/YYYY + ISO)
    parsed = pd.to_datetime(out[column], errors="coerce", dayfirst=dayfirst, format="mixed")
    iso = parsed.dt.strftime("%Y-%m-%d")
    changes, quarantined = [], []
    for i, (orig, new) in enumerate(zip(out[column], iso)):
        k = _key(out, i, key_col)
        has_orig = pd.notna(orig) and str(orig).strip() != ""
        if pd.isna(new) and has_orig:
            quarantined.append({"row_key": k, "column": column,
                                "reason": "unparseable date", "value": orig})
        elif pd.notna(new) and str(orig).strip()[:10] != new:  # [:10] avoids false +ve on Timestamps
            changes.append(Change(column, k, "normalize_date", orig, new))
    out[column] = iso.where(iso.notna(), None)
    return CleanResult(out, changes,
                       {"parsed": int(iso.notna().sum()), "quarantined": len(quarantined)},
                       [], quarantined)


def normalize_phones(df: pd.DataFrame, column: str, *, key_col: str | None = None) -> CleanResult:
    out = df.copy()
    changes, quarantined, vals = [], [], []
    for i, orig in enumerate(out[column]):
        k = _key(out, i, key_col)
        if pd.isna(orig) or str(orig).strip() == "":
            vals.append(None); continue
        digits = re.sub(r"\D", "", str(orig))
        if len(digits) == 12 and digits.startswith("91"):
            canon = "+" + digits
        elif len(digits) == 11 and digits.startswith("0"):
            canon = "+91" + digits[1:]
        elif len(digits) == 10:
            canon = "+91" + digits
        else:
            vals.append(str(orig))
            quarantined.append({"row_key": k, "column": column,
                                "reason": f"bad phone length ({len(digits)})", "value": orig})
            continue
        vals.append(canon)
        if canon != str(orig):
            changes.append(Change(column, k, "normalize_phone", orig, canon))
    out[column] = vals
    return CleanResult(out, changes,
                       {"normalized": len(changes), "flagged": len(quarantined)}, [], quarantined)


def normalize_money(df: pd.DataFrame, column: str, *, key_col: str | None = None) -> CleanResult:
    out = df.copy()
    changes, quarantined, vals = [], [], []
    for i, orig in enumerate(out[column]):
        k = _key(out, i, key_col)
        if pd.isna(orig) or str(orig).strip() == "":
            vals.append(None); continue
        cleaned = re.sub(r"[^\d.\-]", "", str(orig))
        try:
            f = float(cleaned)
            vals.append(f)
            if str(orig) != str(f):
                changes.append(Change(column, k, "normalize_money", orig, f))
        except ValueError:
            vals.append(None)
            quarantined.append({"row_key": k, "column": column,
                                "reason": "unparseable money", "value": orig})
    out[column] = vals
    return CleanResult(out, changes,
                       {"parsed": len(vals) - len(quarantined), "quarantined": len(quarantined)},
                       [], quarantined)


# ---- Stage 2: value standardization ----

def auto_value_map(series) -> dict:
    """Derive a {raw: {canonical, score}} map from a column's OWN values: group variants by
    a normalized key, canonical = the most-frequent original spelling in the group. Used
    when the planner asks to standardize a column without supplying an explicit mapping."""
    from collections import Counter, defaultdict
    groups: dict[str, list[str]] = defaultdict(list)
    for v in series.dropna():
        groups[re.sub(r"\s+", " ", str(v).strip().lower())].append(str(v))
    mapping: dict = {}
    for members in groups.values():
        # canonical = most-frequent *whitespace-stripped* form, so variants collapse to a
        # clean value (" Robbery " and "robbery" both -> "Robbery") not a messy raw spelling
        canon = Counter(re.sub(r"\s+", " ", m.strip()) for m in members).most_common(1)[0][0]
        for m in set(members):
            mapping[m] = {"canonical": canon, "score": 100}
    return mapping


def build_value_map(values, canonical: list[str], *, threshold: int = 85) -> dict:
    """Map each distinct raw value to its closest canonical term via rapidfuzz.
    Below threshold -> canonical=None (left for the agent to adjudicate in Plan 2).
    Matching is case-insensitive (processor=str.lower) so 'theft' maps to 'Theft'."""
    mapping: dict = {}
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        match, score, _ = process.extractOne(str(v).strip(), canonical,
                                              scorer=fuzz.WRatio, processor=str.lower)
        mapping[v] = {"canonical": match if score >= threshold else None, "score": round(score, 1)}
    return mapping


def standardize_values(df: pd.DataFrame, column: str, mapping: dict, *,
                       key_col: str | None = None) -> CleanResult:
    out = df.copy()
    changes, vals, unmapped = [], [], set()
    for i, orig in enumerate(out[column]):
        k = _key(out, i, key_col)
        entry = mapping.get(orig)
        canon = entry["canonical"] if entry else None
        if canon is not None:
            vals.append(canon)
            if canon != orig:
                changes.append(Change(column, k, "standardize", orig, canon))
        else:
            vals.append(orig)
            if orig is not None and str(orig).strip():
                unmapped.add(orig)
    out[column] = vals
    return CleanResult(out, changes,
                       {"standardized": len(changes), "unmapped_distinct": len(unmapped)},
                       [f"{len(unmapped)} distinct values unmapped"] if unmapped else [], [])


# ---- Stage 3: entity resolution ----

def _norm_name(s: str) -> str:
    # Keep letters of ANY script (Kannada/Tamil/Devanagari names must not vanish) + spaces;
    # drop digits/punctuation. .isalpha() is Unicode-aware.
    kept = "".join(ch for ch in str(s).lower() if ch.isalpha() or ch.isspace())
    return re.sub(r"\s+", " ", kept).strip()


def resolve_persons(df: pd.DataFrame, name_col: str, *, locality_col: str | None = None,
                    id_col: str | None = None, threshold: int = 88) -> CleanResult:
    """Cluster near-duplicate person names (corroborated by locality when given) and
    assign each cluster a canonical id in a new 'person_canonical' column. Blocked by
    the first 4 chars of the normalized name to stay near-linear."""
    out = df.copy()
    norm = out[name_col].fillna("").map(_norm_name)
    person_canon: list[str | None] = [None] * len(out)
    changes: list[Change] = []
    blocks: dict[str, list[int]] = {}
    for i, k in enumerate(norm):
        if k:
            blocks.setdefault(k[:4], []).append(i)

    cluster_id = 0
    merged = 0
    for _, members in blocks.items():
        reps: list[tuple[str, str]] = []  # (norm_name, cluster_id)
        local: dict[str, list[int]] = {}
        for i in members:
            ni = norm.iloc[i]
            match_cid = None
            for rn, cid in reps:
                if fuzz.token_sort_ratio(ni, rn) >= threshold:
                    if locality_col is None or str(out[locality_col].iloc[i]) == \
                            str(out[locality_col].iloc[local[cid][0]]):
                        match_cid = cid
                        break
            if match_cid is None:
                cid = f"PC{cluster_id:06d}"; cluster_id += 1
                reps.append((ni, cid)); local[cid] = [i]
            else:
                local[match_cid].append(i)
        for cid, idxs in local.items():
            rep_name = out[name_col].iloc[idxs[0]]
            if len(idxs) > 1:
                merged += 1
            for i in idxs:
                person_canon[i] = cid
                if len(idxs) > 1 and str(out[name_col].iloc[i]) != str(rep_name):
                    changes.append(Change(name_col, _key(out, i, id_col),
                                          "merge_person", out[name_col].iloc[i], rep_name))
    out["person_canonical"] = person_canon
    return CleanResult(out, changes,
                       {"clusters": cluster_id, "merged_clusters": merged}, [], [])


# ---- Stage 4: missing / invalid / dedup ----

def handle_missing(df: pd.DataFrame, column: str, *, policy: str = "flag",
                   required: bool = False, valid_range: tuple | None = None,
                   impute=None, key_col: str | None = None) -> CleanResult:
    out = df.copy()
    drop_idx, quarantined, changes = [], [], []
    for i, v in enumerate(out[column]):
        k = _key(out, i, key_col)
        bad_missing = (pd.isna(v) or str(v).strip() == "") and required
        bad_range = (valid_range is not None and pd.notna(v)
                     and not (valid_range[0] <= v <= valid_range[1]))
        if not (bad_missing or bad_range):
            continue
        reason = "missing required" if bad_missing else "out of range"
        if policy == "drop":
            drop_idx.append(i)
            quarantined.append({"row_key": k, "column": column, "reason": reason,
                                "row": out.iloc[i].to_dict()})
        elif policy == "impute" and impute is not None:
            changes.append(Change(column, k, "impute", v, impute))
            out.at[out.index[i], column] = impute
        else:  # flag
            quarantined.append({"row_key": k, "column": column,
                                "reason": f"flagged: {reason}", "value": v})
    if drop_idx:
        out = out.drop(out.index[drop_idx]).reset_index(drop=True)
    return CleanResult(out, changes,
                       {"dropped": len(drop_idx), "flagged": len(quarantined) - len(drop_idx)},
                       [], quarantined)


def dedupe_rows(df: pd.DataFrame, key_cols: list[str], *, key_col: str | None = None) -> CleanResult:
    out = df.copy()
    dup_mask = out.duplicated(subset=key_cols, keep="first")
    quarantined = [{"row_key": _key(out, i, key_col),
                    "reason": f"duplicate of first {key_cols}", "row": out.iloc[i].to_dict()}
                   for i in range(len(out)) if dup_mask.iloc[i]]
    out = out[~dup_mask].reset_index(drop=True)
    return CleanResult(out, [], {"dropped": int(dup_mask.sum())}, [], quarantined)
