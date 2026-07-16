"""Cheap per-column digest the cleaning agent reasons over — never raw rows, so cost is
constant regardless of table size (large frames are sampled)."""
from __future__ import annotations

import pandas as pd


def profile_digest(df: pd.DataFrame, *, key_col: str | None = None,
                   max_distinct: int = 25, sample: int = 20000) -> dict:
    d = df if len(df) <= sample else df.sample(sample, random_state=0)
    cols = []
    for c in df.columns:
        s = d[c]
        col = {"name": c, "dtype": str(s.dtype),
               "null_pct": round(float(s.isna().mean()), 3),
               "distinct": int(s.nunique(dropna=True)),
               "samples": [str(v) for v in s.dropna().unique()[:5]]}
        parsed = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=True)
        col["date_parse_rate"] = round(float(parsed.notna().mean()), 3)
        if s.dtype == object:
            digits = s.dropna().astype(str).str.replace(r"\D", "", regex=True)
            col["phone_like_rate"] = (round(float((digits.str.len() == 10).mean()), 3)
                                      if len(digits) else 0.0)
        if 0 < col["distinct"] <= max_distinct:
            col["values"] = [str(v) for v in s.dropna().unique()[:max_distinct]]
        cols.append(col)
    return {"rows": int(len(df)), "duplicate_rows": int(df.duplicated().sum()),
            "key_col": key_col, "columns": cols}
