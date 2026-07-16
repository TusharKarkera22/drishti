import pandas as pd
from app.services import cleaning as C


def test_cleanresult_holds_df_and_audit():
    df = pd.DataFrame({"a": [1]})
    r = C.CleanResult(df=df)
    assert r.df is df
    assert r.changes == [] and r.quarantined == [] and r.warnings == []
    ch = C.Change(column="a", row_key="0", op="x", before=1, after=2)
    assert ch.column == "a" and ch.before == 1


def test_normalize_dates_mixed_formats_and_quarantine():
    df = pd.DataFrame({"fir": ["A", "B", "C"],
                       "d": ["15/03/2024", "2024-03-16", "not-a-date"]})
    r = C.normalize_dates(df, "d", key_col="fir")
    assert list(r.df["d"]) == ["2024-03-15", "2024-03-16", None]
    assert r.quarantined[0]["row_key"] == "C" and "unparseable" in r.quarantined[0]["reason"]
    assert any(c.op == "normalize_date" for c in r.changes)


def test_normalize_phones_canonical_plus91():
    df = pd.DataFrame({"id": ["1", "2", "3", "4"],
                       "p": ["9876543210", "+91 98765 43210", "098765 43210", "123"]})
    r = C.normalize_phones(df, "p", key_col="id")
    assert list(r.df["p"])[:3] == ["+919876543210"] * 3
    assert r.quarantined[0]["row_key"] == "4"


def test_normalize_money_to_float():
    df = pd.DataFrame({"amt": ["₹1,200.50", "  2000 ", "", "abc"]})
    r = C.normalize_money(df, "amt")
    assert list(r.df["amt"])[:2] == [1200.50, 2000.0]
    assert pd.isna(r.df["amt"].iloc[2])
    assert r.quarantined[0]["reason"].startswith("unparseable")


def test_build_value_map_fuzzy():
    canon = ["Theft", "Cybercrime", "Assault"]
    m = C.build_value_map(["theft", "THEFT - residential", "cyber crime", "zzz"], canon, threshold=80)
    assert m["theft"]["canonical"] == "Theft"
    assert m["cyber crime"]["canonical"] == "Cybercrime"
    assert m["zzz"]["canonical"] is None  # below threshold -> left for the agent


def test_auto_value_map_picks_most_frequent():
    s = pd.Series(["Theft", "Theft", "theft", "THEFT", "Cyber"])
    m = C.auto_value_map(s)
    assert m["theft"]["canonical"] == "Theft" and m["THEFT"]["canonical"] == "Theft"
    assert m["Cyber"]["canonical"] == "Cyber"


def test_standardize_values_applies_map():
    df = pd.DataFrame({"id": ["1", "2", "3"], "cat": ["theft", "cyber crime", "zzz"]})
    mp = {"theft": {"canonical": "Theft", "score": 95},
          "cyber crime": {"canonical": "Cybercrime", "score": 92},
          "zzz": {"canonical": None, "score": 10}}
    r = C.standardize_values(df, "cat", mp, key_col="id")
    assert list(r.df["cat"]) == ["Theft", "Cybercrime", "zzz"]
    assert r.stats["standardized"] == 2 and r.stats["unmapped_distinct"] == 1


def test_resolve_persons_merges_variants():
    df = pd.DataFrame({
        "pid": ["P1", "P2", "P3", "P4"],
        "name": ["Manjunath Gowda", "Manjunath Gowda B", "Manjunath  Gowda", "Asha Rao"],
        "loc": ["Udupi", "Udupi", "Udupi", "Mysuru"],
    })
    r = C.resolve_persons(df, "name", locality_col="loc", id_col="pid", threshold=85)
    canon = dict(zip(df["pid"], r.df["person_canonical"]))
    assert canon["P1"] == canon["P2"] == canon["P3"]   # three variants -> one person
    assert canon["P4"] != canon["P1"]                  # different person
    assert r.stats["merged_clusters"] == 1
    assert any(c.op == "merge_person" for c in r.changes)


def test_handle_missing_flag_and_drop():
    df = pd.DataFrame({"id": ["1", "2", "3"], "x": [10, None, 999]})
    r = C.handle_missing(df, "x", policy="drop", required=True, valid_range=(0, 100), key_col="id")
    assert list(r.df["id"]) == ["1"]
    reasons = {q["row_key"]: q["reason"] for q in r.quarantined}
    assert "missing" in reasons["2"] and "out of range" in reasons["3"]


def test_handle_missing_flag_and_impute():
    df = pd.DataFrame({"id": ["1", "2"], "x": [None, 5]})
    flagged = C.handle_missing(df, "x", policy="flag", required=True, key_col="id")
    assert len(flagged.df) == 2 and flagged.quarantined[0]["reason"].startswith("flagged")
    imputed = C.handle_missing(df, "x", policy="impute", required=True, impute=0, key_col="id")
    assert imputed.df["x"].iloc[0] == 0 and any(c.op == "impute" for c in imputed.changes)


def test_resolve_persons_keeps_non_latin_names():
    df = pd.DataFrame({"pid": ["P1", "P2"], "name": ["ಮಂಜುನಾಥ ಗೌಡ", "ಮಂಜುನಾಥ ಗೌಡ"]})
    r = C.resolve_persons(df, "name", id_col="pid", threshold=85)
    assert all(c is not None for c in r.df["person_canonical"])  # Kannada names not dropped
    assert r.df["person_canonical"].iloc[0] == r.df["person_canonical"].iloc[1]


def test_dedupe_rows_quarantines_duplicates():
    df = pd.DataFrame({"fir": ["A", "A", "B"], "v": [1, 1, 2]})
    r = C.dedupe_rows(df, ["fir"], key_col="fir")
    assert list(r.df["fir"]) == ["A", "B"]
    assert r.quarantined[0]["reason"].startswith("duplicate")


def test_dirty_dataframe_injects_and_records():
    import scripts.dirty_data as D
    clean = pd.DataFrame({
        "fir": [f"F{i}" for i in range(50)],
        "occurrence_ts": ["2024-03-15"] * 50,
        "phone": ["9876543210"] * 50,
        "crime_group": ["Theft"] * 50,
    })
    messy, truth = D.dirty_dataframe(clean, seed=7,
                                     date_cols=["occurrence_ts"], phone_cols=["phone"],
                                     cat_cols=["crime_group"], required_cols=["phone"])
    assert len(messy) >= len(clean)                       # may add duplicate rows
    assert (messy["occurrence_ts"] != "2024-03-15").any() # some dates reformatted
    assert truth["date_formats_changed"] > 0


def test_score_recovers_dates_and_dupes():
    import scripts.dirty_data as D
    import scripts.score_cleaning as S
    clean = pd.DataFrame({
        "fir": [f"F{i}" for i in range(40)],
        "occurrence_ts": ["2024-03-15"] * 40,
        "phone": ["9876543210"] * 40,
    })
    messy, _ = D.dirty_dataframe(clean, seed=3, date_cols=["occurrence_ts"], phone_cols=["phone"])
    score = S.score(clean, messy, key="fir", date_cols=["occurrence_ts"], phone_cols=["phone"])
    assert score["date_recovery"] >= 0.95
    assert score["rows_after_dedup"] == 40
