"""Agentic cleaning loop: profile -> (plan -> execute -> assess) x<=2 -> report.

The LLM is INJECTED (llm_fn: prompt -> text) so the loop is unit-testable with canned
responses; it only ever sees the digest + change summaries, never raw rows. Deterministic
cleaners (services.cleaning) do the actual work."""
from __future__ import annotations

import json
import re

from app.services import cleaning, digest as digest_mod

OP_FUNCS = {
    "normalize_dates":    lambda df, p, k: cleaning.normalize_dates(df, p["column"], key_col=k),
    "normalize_phones":   lambda df, p, k: cleaning.normalize_phones(df, p["column"], key_col=k),
    "normalize_money":    lambda df, p, k: cleaning.normalize_money(df, p["column"], key_col=k),
    "standardize_values": lambda df, p, k: cleaning.standardize_values(
        df, p["column"], p.get("mapping") or cleaning.auto_value_map(df[p["column"]]), key_col=k),
    "resolve_persons":    lambda df, p, k: cleaning.resolve_persons(df, p["column"], locality_col=p.get("locality_col"), id_col=k),
    "handle_missing":     lambda df, p, k: cleaning.handle_missing(
        df, p["column"], policy=p.get("policy", "flag"), required=p.get("required", False),
        valid_range=tuple(p["valid_range"]) if p.get("valid_range") else None, key_col=k),
    "dedupe_rows":        lambda df, p, k: cleaning.dedupe_rows(
        df, p.get("key_cols") or ([k] if k else list(df.columns)), key_col=k),
}
VALID_OPS = set(OP_FUNCS)


def execute_plan(df, plan, key_col):
    changes, quarantined, applied = [], [], []
    for op in plan:
        fn = OP_FUNCS.get(op.get("op"))
        if fn is None:
            continue  # unknown / unvalidated op -> skip (never execute)
        try:
            r = fn(df, op, key_col)
            df = r.df
            changes += r.changes
            quarantined += r.quarantined
            applied.append({"op": op["op"], "column": op.get("column"), "stats": r.stats})
        except Exception as e:  # surface the failure, never crash the job
            applied.append({"op": op.get("op"), "error": str(e)})
    return df, changes, quarantined, applied


# ---- LLM JSON contract (free text -> validated JSON, safe fallback) ----

def _extract_json(text):
    if not text:
        return None
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _validate_plan(obj):
    if not isinstance(obj, list):
        return []
    return [op for op in obj if isinstance(op, dict) and op.get("op") in VALID_OPS]


def _plan_prompt(dg):
    return ("You are a data-cleaning planner for police records. From this column DIGEST, "
            'output ONLY a JSON array of cleaning ops, each like {"op":..,"column":..}. '
            "Guidance: normalize_dates for any column with date_parse_rate>0.5; "
            "normalize_phones for columns with phone_like_rate>0.3; standardize_values for "
            "low-cardinality text columns that list 'values' (casing/spelling variants); "
            "resolve_persons for a person-name column; normalize_money for money/amount "
            "columns; handle_missing for columns with high null_pct; and ALWAYS dedupe_rows. "
            f"Valid ops: {sorted(VALID_OPS)}. Digest:\n{json.dumps(dg)[:6000]}")


def _assess_prompt(dg, applied):
    return ("Given the POST-clean digest and what was applied, reply ONLY JSON: "
            '{"done":true,"issues":[...]} if clean enough, else '
            '{"done":false,"corrective_plan":[<ops>]}. '
            f"Applied: {json.dumps(applied)[:2000]}\nDigest:\n{json.dumps(dg)[:4000]}")


def propose_plan(dg, llm_fn):
    return _validate_plan(_extract_json(llm_fn(_plan_prompt(dg))) or [])


def assess(dg, applied, llm_fn):
    obj = _extract_json(llm_fn(_assess_prompt(dg, applied))) or {}
    if isinstance(obj, dict) and obj.get("done"):
        return {"done": True, "issues": obj.get("issues", [])}
    cp = obj.get("corrective_plan", []) if isinstance(obj, dict) else []
    return {"done": False, "corrective_plan": _validate_plan(cp)}


def _final_report(log, llm_fn):
    try:
        return llm_fn("Write a 3-4 sentence plain-English cleaning report (what was fixed, "
                      f"what was quarantined and why) from this log:\n{json.dumps(log)[:4000]}")
    except Exception:
        return "Cleaning complete. See the per-stage audit and quarantine log."


# ---- the loop ----

def run_intake(df, *, key_col, llm_fn, max_iter=2, on_progress=None):
    log = {"iterations": [], "report": ""}
    quarantined = []
    plan = propose_plan(digest_mod.profile_digest(df, key_col=key_col), llm_fn)
    for it in range(max_iter):
        df, changes, quar, applied = execute_plan(df, plan, key_col)
        quarantined += quar
        post = digest_mod.profile_digest(df, key_col=key_col)
        a = assess(post, applied, llm_fn)
        log["iterations"].append({"iteration": it + 1, "plan": plan, "applied": applied,
                                  "n_changes": len(changes), "n_quarantined": len(quar),
                                  "assessment": a})
        if on_progress:
            on_progress(log["iterations"][-1])
        if a["done"] or it == max_iter - 1 or not a["corrective_plan"]:
            break
        plan = a["corrective_plan"]
    log["report"] = _final_report(log, llm_fn)
    log["cleaned_df"] = df
    log["quarantined"] = quarantined
    return log
