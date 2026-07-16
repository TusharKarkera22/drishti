"""Run the cleaners over a dirtied dataset and measure recovery vs the clean ground
truth. Used as a test gate AND as a demo stat (shown in the Intake UI)."""
from __future__ import annotations

import pandas as pd

from app.services import cleaning as C


def score(clean: pd.DataFrame, messy: pd.DataFrame, *, key: str,
          date_cols=(), phone_cols=()) -> dict:
    df = messy
    for col in date_cols:
        df = C.normalize_dates(df, col, key_col=key).df
    for col in phone_cols:
        df = C.normalize_phones(df, col, key_col=key).df
    df = C.dedupe_rows(df, [key], key_col=key).df

    truth = clean.set_index(key)
    got = df.set_index(key)
    result = {"rows_after_dedup": len(df)}
    for col in date_cols:
        # Compare on canonical date: normalize the ground truth the same way the cleaner
        # does (ground truth may carry a time component the cleaner drops to a date).
        t = pd.to_datetime(truth[col], errors="coerce").dt.strftime("%Y-%m-%d")  # truth is canonical
        joined = pd.DataFrame({"t": t, "g": got[col]}).dropna()
        match = (joined["t"] == joined["g"]).mean() if len(joined) else 0.0
        result["date_recovery"] = round(float(match), 3)
    return result


if __name__ == "__main__":  # CLI: python scripts/score_cleaning.py ksp-crime incidents
    import sys
    import scripts.dirty_data as D
    from app.core import store
    ds, table = sys.argv[1], sys.argv[2]
    clean = pd.read_parquet(store.table_path(ds, table))
    messy, _ = D.dirty_dataframe(clean, seed=42,
                                 date_cols=[c for c in ["occurrence_ts"] if c in clean],
                                 phone_cols=[c for c in clean.columns if "phone" in c.lower()])
    print(score(clean, messy, key=clean.columns[0],
                date_cols=[c for c in ["occurrence_ts"] if c in clean],
                phone_cols=[c for c in clean.columns if "phone" in c.lower()]))
