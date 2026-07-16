import pandas as pd

from app.services import digest as DG
from app.services import intake as IN


def test_profile_digest_flags_formats():
    df = pd.DataFrame({"fir": ["A", "B", "C"], "d": ["15/03/2024", "2024-03-16", "x"],
                       "cat": ["Theft", "theft", "THEFT"], "phone": ["9876543210", "98765", "abc"]})
    dg = DG.profile_digest(df, key_col="fir")
    assert dg["rows"] == 3
    col = {c["name"]: c for c in dg["columns"]}
    assert col["d"]["date_parse_rate"] >= 0.6                       # 2 of 3 parse
    assert col["cat"]["distinct"] == 3 and "values" in col["cat"]   # low-cardinality -> values
    assert col["phone"]["phone_like_rate"] > 0


def test_execute_plan_routes_to_cleaners():
    df = pd.DataFrame({"fir": ["A", "B", "B"], "d": ["15/03/2024", "2024-03-16", "2024-03-16"]})
    plan = [{"op": "normalize_dates", "column": "d"}, {"op": "dedupe_rows", "key_cols": ["fir"]},
            {"op": "bogus_op", "column": "d"}]
    out, changes, quar, applied = IN.execute_plan(df, plan, key_col="fir")
    assert list(out["d"])[0] == "2024-03-15"
    assert len(out) == 2                                            # dedup dropped the dup
    assert [a["op"] for a in applied if "error" not in a] == ["normalize_dates", "dedupe_rows"]
    assert all(a["op"] != "bogus_op" for a in applied)             # unknown op skipped


def test_propose_plan_parses_and_validates():
    dg = {"columns": [{"name": "d", "date_parse_rate": 0.6}]}
    good = lambda _: 'Here is the plan:\n[{"op":"normalize_dates","column":"d"},{"op":"nope"}]'
    assert IN.propose_plan(dg, good) == [{"op": "normalize_dates", "column": "d"}]  # invalid dropped
    assert IN.propose_plan(dg, lambda _: "sorry no json") == []                     # malformed -> no-op


def test_assess_done_vs_corrective():
    done = lambda _: '{"done": true, "issues": []}'
    fix = lambda _: '{"done": false, "corrective_plan":[{"op":"dedupe_rows","key_cols":["fir"]}]}'
    assert IN.assess({}, [], done)["done"] is True
    a = IN.assess({}, [], fix)
    assert a["done"] is False and a["corrective_plan"][0]["op"] == "dedupe_rows"


def test_run_intake_two_iterations():
    df = pd.DataFrame({"fir": ["A", "B", "B"], "d": ["15/03/2024", "2024-03-16", "2024-03-16"]})
    calls = {"n": 0}

    def fake(prompt):
        if "planner" in prompt:
            return '[{"op":"normalize_dates","column":"d"}]'
        if "POST-clean" in prompt:
            calls["n"] += 1
            return ('{"done":false,"corrective_plan":[{"op":"dedupe_rows","key_cols":["fir"]}]}'
                    if calls["n"] == 1 else '{"done":true,"issues":[]}')
        return "report text"

    log = IN.run_intake(df, key_col="fir", llm_fn=fake, max_iter=2)
    assert len(log["cleaned_df"]) == 2                 # dedup happened in iteration 2
    assert log["report"] == "report text"
    assert len(log["iterations"]) == 2


def test_intake_job_runs_to_done(monkeypatch):
    import time
    import app.routers.intake as R
    df = pd.DataFrame({"fir": ["A", "B", "B"], "d": ["15/03/2024", "2024-03-16", "2024-03-16"]})
    monkeypatch.setattr(R, "_llm_fn",
                        lambda p: '[{"op":"dedupe_rows"}]' if "planner" in p else '{"done":true}')
    monkeypatch.setattr(R, "_write_cleaned_dataset", lambda d, name: "ds_test")
    job_id = R._start_job(df, key_col="fir", name="t")
    for _ in range(80):
        if R.JOBS[job_id]["done"]:
            break
        time.sleep(0.05)
    j = R.JOBS[job_id]
    assert j["done"] and j["status"] == "complete"
    assert j["output_dataset_id"] == "ds_test" and j["rows_out"] == 2
