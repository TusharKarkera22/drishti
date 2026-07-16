"""Inject realistic mess into a clean DataFrame so the cleaning pipeline can be
verified (clean -> dirty -> clean -> compare). Importable (dirty_dataframe) and a CLI
that writes a messy .xlsx next to a dataset. Deterministic given a seed."""
from __future__ import annotations

import random
import re

import pandas as pd

_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y"]


def _reformat_date(iso: str, rnd: random.Random) -> str:
    try:
        d = pd.to_datetime(iso)
    except Exception:
        return iso
    return d.strftime(rnd.choice(_DATE_FORMATS))


def _mess_phone(p: str, rnd: random.Random) -> str:
    digits = re.sub(r"\D", "", str(p))[-10:]
    style = rnd.choice(["+91 ", "0", "", "+91-"])
    if style == "0":
        return "0" + digits
    return f"{style}{digits[:5]} {digits[5:]}" if style else digits


def _mess_name(n: str, rnd: random.Random) -> str:
    choice = rnd.choice(["suffix", "spaces", "case"])
    if choice == "suffix":
        return n + " " + rnd.choice(["B", "S/O Kumar", "@alias"])
    if choice == "spaces":
        return n.replace(" ", "  ")
    return n.upper()


def _mess_category(c: str, rnd: random.Random) -> str:
    return rnd.choice([c.lower(), c.upper(), c + " - misc", " " + c + " "])


def dirty_dataframe(df: pd.DataFrame, *, seed: int = 0, rate: float = 0.3,
                    date_cols=(), phone_cols=(), cat_cols=(), name_cols=(),
                    required_cols=()) -> tuple[pd.DataFrame, dict]:
    rnd = random.Random(seed)
    out = df.copy()
    truth = {"date_formats_changed": 0, "phones_messed": 0, "names_varied": 0,
             "categories_messed": 0, "blanked": 0, "duplicated_rows": 0}

    def maybe(col_list, fn, counter):
        for col in col_list:
            for i in range(len(out)):
                if rnd.random() < rate and pd.notna(out[col].iloc[i]):
                    out.at[out.index[i], col] = fn(out[col].iloc[i], rnd)
                    truth[counter] += 1

    maybe(date_cols, _reformat_date, "date_formats_changed")
    maybe(phone_cols, _mess_phone, "phones_messed")
    maybe(cat_cols, _mess_category, "categories_messed")
    maybe(name_cols, _mess_name, "names_varied")
    for col in required_cols:  # blank some required fields
        for i in range(len(out)):
            if rnd.random() < rate * 0.3:
                out.at[out.index[i], col] = None
                truth["blanked"] += 1
    # inject a few exact duplicate rows
    dup_n = max(1, int(len(out) * 0.02))
    dups = out.sample(n=dup_n, random_state=seed)
    out = pd.concat([out, dups], ignore_index=True)
    truth["duplicated_rows"] = dup_n
    return out.sample(frac=1, random_state=seed).reset_index(drop=True), truth


if __name__ == "__main__":  # CLI: python scripts/dirty_data.py ksp-crime incidents
    import sys
    from app.core import store
    ds, table = sys.argv[1], sys.argv[2]
    clean = pd.read_parquet(store.table_path(ds, table))
    messy, truth = dirty_dataframe(
        clean, seed=42,
        date_cols=[c for c in ["occurrence_ts", "registration_ts"] if c in clean],
        phone_cols=[c for c in clean.columns if "phone" in c.lower()],
        cat_cols=[c for c in ["crime_group", "crime_head"] if c in clean],
    )
    messy.to_excel(f"/tmp/messy_{ds}_{table}.xlsx", index=False)
    print("wrote messy file:", truth)
