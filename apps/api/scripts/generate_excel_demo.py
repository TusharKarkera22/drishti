"""Generate 'Excel silo' demo files for live DRISHTI ingest in the demo.

Models the datathon's OFFICIAL Police FIR ER schema (CaseMaster, Accused,
Victim, ComplainantDetails + the lookups), but as a real district keeps it:
flat Excel sheets with the schema's field names and the human-readable values a
clerk actually types (clerks enter "Heinous", not GravityOffenceID=1). That makes
the upload faithful to the ER diagram AND render names — raw normalized FK
integers would just show as numbers in the generic-upload path.

Four silos, linked by "FIR Number" (the platform links multiple uploaded files
into one dataset on the shared key):
  - Crime_Cases.xlsx   (CaseMaster + Inv_OccuranceTime — fact; dashboard/map/insights)
  - Accused.xlsx       (Accused + Mobile/Address — the network: shared mobile = ring)
  - Victims.xlsx       (Victim)
  - Complainants.xlsx  (ComplainantDetails — occupation/religion/caste socio-demographics)

Planted so the demo lights up: a Cyber Crime spike in Bengaluru City over the last
4 weeks, a 5-person burglary ring sharing 2 mobiles across ~16 cases, heinous
cases (Murder/Robbery), and A/B/C final-report disposal.

Run:  cd apps/api && .venv/bin/python scripts/generate_excel_demo.py
Out:  samples/excel-silos/*.xlsx
"""

from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

rng = np.random.default_rng(7)
random.seed(7)
fake = Faker("en_IN")
Faker.seed(7)

END = dt.datetime(2026, 6, 25)
START = END - dt.timedelta(days=365)
N = 3000  # incidents — small so live upload + profiling + graph build is snappy

DISTRICTS = {  # name: (lat, lng, weight, FIR prefix)
    "Bengaluru City": (12.9716, 77.5946, 30, "BLR"),
    "Mysuru": (12.2958, 76.6394, 10, "MYS"),
    "Mangaluru City": (12.8703, 74.8420, 8, "MNG"),
    "Belagavi": (15.8497, 74.4977, 7, "BGM"),
    "Hubballi-Dharwad": (15.3647, 75.1240, 7, "HBL"),
    "Kalaburagi": (17.3297, 76.8343, 6, "KLB"),
    "Tumakuru": (13.3392, 77.1010, 6, "TMK"),
    "Shivamogga": (13.9299, 75.5681, 5, "SMG"),
    "Davanagere": (14.4644, 75.9218, 5, "DVG"),
    "Ballari": (15.1394, 76.9214, 5, "BLY"),
}

# Official-style Crime Major Head -> Minor Heads, with (weight, peak hours, avg loss ₹)
HEADS = {
    "Crimes Against Property": (24, [1, 2, 3, 19, 22], 90000,
        ["House Break-in (Night)", "House Break-in (Day)", "Theft", "Robbery", "Dacoity", "Two-Wheeler Theft"]),
    "Crimes Against Body": (16, [20, 22, 0, 2], 0,
        ["Murder", "Attempt to Murder", "Grievous Hurt", "Simple Hurt"]),
    "Cyber Crime": (14, [11, 15, 17], 150000,
        ["UPI Fraud", "OTP Scam", "Investment App Fraud", "Job Fraud", "Sextortion"]),
    "Economic Offences": (10, [11, 14, 16], 280000,
        ["Cheating", "Forgery", "Chit Fund Fraud", "Criminal Breach of Trust"]),
    "Crimes Against Women": (10, [20, 21, 22], 0,
        ["Dowry Harassment", "Cruelty by Husband", "Assault on Woman"]),
    "Narcotic Crimes": (5, [21, 23, 1], 0, ["NDPS Possession", "NDPS Peddling"]),
    "Crimes Against Public Order": (5, [16, 18, 20], 0, ["Rioting", "Unlawful Assembly"]),
    "Missing Persons": (6, [8, 12, 18], 0, ["Missing Adult", "Missing Minor"]),
}
HEINOUS = {"Murder", "Attempt to Murder", "Robbery", "Dacoity", "NDPS Peddling", "Assault on Woman"}
SECTIONS = {
    "Murder": "IPC 302", "Attempt to Murder": "IPC 307", "Grievous Hurt": "IPC 326",
    "Simple Hurt": "IPC 323", "House Break-in (Night)": "IPC 457, IPC 380",
    "House Break-in (Day)": "IPC 454, IPC 380", "Theft": "IPC 379", "Robbery": "IPC 392",
    "Dacoity": "IPC 395", "Two-Wheeler Theft": "IPC 379", "UPI Fraud": "IPC 420, IT Act 66D",
    "OTP Scam": "IPC 419, IT Act 66C", "Investment App Fraud": "IPC 420, IT Act 66D",
    "Job Fraud": "IPC 420", "Sextortion": "IT Act 67, IPC 384", "Cheating": "IPC 420",
    "Forgery": "IPC 465", "Chit Fund Fraud": "IPC 406, IPC 420", "Criminal Breach of Trust": "IPC 406",
    "Dowry Harassment": "IPC 498A, DP Act 4", "Cruelty by Husband": "IPC 498A",
    "Assault on Woman": "IPC 354", "NDPS Possession": "NDPS Act 20", "NDPS Peddling": "NDPS Act 21",
    "Rioting": "IPC 147", "Unlawful Assembly": "IPC 143", "Missing Adult": "Man/Woman Missing",
    "Missing Minor": "IPC 363",
}
# Case Status -> Final Report Type (ChargesheetDetails.cstype A/B/C)
STATUS_REPORT = [
    ("Under Investigation", 0.40, ""),
    ("Charge Sheeted", 0.28, "A - Chargesheet"),
    ("Closed - Detected", 0.16, "A - Chargesheet"),
    ("Closed - Undetected", 0.11, "C - Undetected"),
    ("Closed - False", 0.05, "B - False Case"),
]
OCCUPATIONS = ["Farmer", "Daily Wage Labourer", "Business", "Government Employee",
               "Private Employee", "Student", "Homemaker", "IT Professional", "Auto Driver", "Shopkeeper"]
RELIGIONS = (["Hindu"] * 6) + (["Muslim"] * 2) + ["Christian", "Jain"]
CASTES = (["General"] * 3) + (["OBC"] * 4) + (["SC"] * 2) + ["ST"]
RANKS = ["PSI", "PI", "ASI", "PC"]


def _ts(peak_hours):
    base = START + dt.timedelta(days=int(rng.integers(0, (END - START).days)))
    hour = int(rng.choice(peak_hours)) if rng.random() < 0.55 else int(rng.integers(0, 24))
    return base.replace(hour=hour, minute=int(rng.integers(0, 60)), second=0, microsecond=0)


def build(rows=N):
    d_names = list(DISTRICTS)
    d_w = np.array([DISTRICTS[d][2] for d in d_names], float); d_w /= d_w.sum()
    h_names = list(HEADS)
    h_w = np.array([HEADS[h][0] for h in h_names], float); h_w /= h_w.sum()
    stations = {d: [f"{d} {n}" for n in ("City PS", "North PS", "South PS", "Rural PS", "Cyber PS")] for d in d_names}
    officers = {d: [f"{random.choice(RANKS)} {fake.name()}" for _ in range(8)] for d in d_names}
    counters: dict[str, int] = {}

    def one(d, head, ts):
        sub = random.choice(HEADS[head][3])
        lat, lng = DISTRICTS[d][0], DISTRICTS[d][1]
        loss = HEADS[head][2]
        counters[d] = counters.get(d, 0) + 1
        firno = f"{DISTRICTS[d][3]}/{ts.year}/{counters[d]:05d}"
        status, _, report = random.choices(
            STATUS_REPORT, [w for _, w, _ in STATUS_REPORT])[0]
        cat = "UDR" if head == "Missing Persons" and rng.random() < 0.5 else (
            "Zero FIR" if rng.random() < 0.03 else "FIR")
        return {
            "FIR Number": firno,
            "Crime Registered Date": (ts + dt.timedelta(hours=float(rng.exponential(14)))).date(),
            "District": d,
            "Police Station": random.choice(stations[d]),
            "Case Category": cat,
            "Gravity of Offence": "Heinous" if sub in HEINOUS else "Non-Heinous",
            "Crime Major Head": head,
            "Crime Minor Head": sub,
            "Acts and Sections": SECTIONS.get(sub, "IPC 379"),
            "Case Status": status,
            "Final Report Type": report,
            "Court": f"{d} JMFC Court",
            "Investigating Officer": random.choice(officers[d]),
            "Incident Date Time": ts,
            "Info Received Date": (ts + dt.timedelta(hours=float(rng.exponential(14)))).date(),
            "Latitude": round(lat + rng.normal(0, 0.05), 6),
            "Longitude": round(lng + rng.normal(0, 0.05), 6),
            "Brief Facts": f"{sub} reported under {head} at {d}.",
        }

    recs = []
    for _ in range(rows):
        d = str(rng.choice(d_names, p=d_w)); head = str(rng.choice(h_names, p=h_w))
        recs.append(one(d, head, _ts(HEADS[head][1])))

    # planted: Cyber Crime spike (~7% of volume), Bengaluru City, last 4 weeks
    for _ in range(int(rows * 0.073)):
        ts = END - dt.timedelta(days=float(rng.integers(0, 28)), hours=float(rng.integers(0, 24)))
        recs.append(one("Bengaluru City", "Cyber Crime", ts))

    cases = pd.DataFrame(recs).sample(frac=1, random_state=7).reset_index(drop=True)
    firs = cases["FIR Number"].tolist()
    fir_head = dict(zip(cases["FIR Number"], cases["Crime Minor Head"]))

    # ---- Accused (Accused table + Mobile/Address enrichment) ----
    n_people = max(rows // 6, 700)
    people = pd.DataFrame({
        "PersonRef": [f"KAR-P{i:06d}" for i in range(n_people)],  # recurring person key
        "Name": [fake.name() for _ in range(n_people)],
        "Age": rng.integers(18, 62, n_people),
        "Gender": rng.choice(["Male", "Female"], n_people, p=[0.86, 0.14]),
        "Mobile": [f"9{rng.integers(100000000, 999999999)}" for _ in range(n_people)],
        "Address": [f"{fake.street_address()}, {rng.choice(d_names)}" for _ in range(n_people)],
    })
    solved_firs = cases[cases["Case Status"].isin(
        ["Charge Sheeted", "Closed - Detected"])]["FIR Number"].tolist()
    w = rng.pareto(2.2, n_people) + 1; w = np.minimum(w, np.percentile(w, 99)); w /= w.sum()
    acc = []

    def _row(f, k, ref, name, age, gender, mobile, addr):
        # "Person Reference ID" recurs for the same offender across FIRs -> the link
        # graph collapses them to one node (repeat-offender tracking) instead of a
        # node per row, which also keeps the network small enough to build live.
        return {"Accused ID": f"ACC{len(acc)+1:06d}", "FIR Number": f,
                "Person Reference ID": ref, "Accused Name": name, "Age": int(age),
                "Gender": gender, "Accused Sorting": f"A{k+1}",
                "Mobile Number": mobile, "Address": addr}

    for f in solved_firs:
        for k in range(int(rng.choice([1, 1, 1, 2, 2, 3]))):
            p = people.iloc[int(rng.choice(n_people, p=w))]
            acc.append(_row(f, k, p.PersonRef, p.Name, p.Age, p.Gender, p.Mobile, p.Address))

    # planted: 5-person burglary ring sharing 2 mobiles across ~16 break-in cases
    ring_mobiles = [f"98861{rng.integers(10000, 99999)}" for _ in range(2)]
    ring = [{"ref": f"KAR-R{i:03d}", "Name": fake.name(), "Age": int(rng.integers(23, 41)),
             "Gender": "Male", "Mobile": ring_mobiles[i % 2],
             "Address": f"{fake.street_address()}, Bengaluru City"} for i in range(5)]
    breakins = [f for f in firs if "Break-in" in fir_head.get(f, "")]
    for f in random.sample(breakins, k=min(16, len(breakins))):
        for k, m in enumerate(random.sample(ring, k=2)):
            acc.append(_row(f, k, m["ref"], m["Name"], m["Age"], m["Gender"], m["Mobile"], m["Address"]))
    accused = pd.DataFrame(acc)

    # ---- Victims ----
    vic = []
    for f in cases.sample(frac=0.65, random_state=11)["FIR Number"]:
        vic.append({"Victim ID": f"VIC{len(vic)+1:06d}", "FIR Number": f,
                    "Victim Name": fake.name(), "Age": int(rng.integers(10, 82)),
                    "Gender": str(rng.choice(["Male", "Female"], p=[0.5, 0.5])),
                    "Is Police Victim": "Yes" if rng.random() < 0.02 else "No"})
    victims = pd.DataFrame(vic)

    # ---- Complainants (socio-demographics) ----
    # ~88% coverage (a realistically incomplete silo) — also keeps complainants
    # smaller than the fact table so crime_cases stays the detected parent/fact.
    comp = []
    for f in cases.sample(frac=0.88, random_state=13)["FIR Number"]:
        comp.append({"Complainant ID": f"CMP{len(comp)+1:06d}", "FIR Number": f,
                     "Complainant Name": fake.name(), "Age": int(rng.integers(18, 75)),
                     "Gender": str(rng.choice(["Male", "Female"], p=[0.6, 0.4])),
                     "Occupation": random.choice(OCCUPATIONS),
                     "Religion": random.choice(RELIGIONS), "Caste": random.choice(CASTES)})
    complainants = pd.DataFrame(comp)
    return cases, accused, victims, complainants


def build_append_month(cases: pd.DataFrame, n_new: int = 500, n_dupe: int = 50) -> pd.DataFrame:
    """Build the monthly "Crime_Cases_Update.xlsx" prop: ~n_new freshly-generated
    rows dated in the 3 weeks after `END` (continuing each district's FIR serial
    so ids don't collide with the base file) plus ~n_dupe rows copied verbatim
    from `cases` (same FIR Number) — the duplicate-FIR dedupe demo for
    `POST /api/ingest/{id}/append`."""
    d_names = list(DISTRICTS)
    d_w = np.array([DISTRICTS[d][2] for d in d_names], float); d_w /= d_w.sum()
    h_names = list(HEADS)
    h_w = np.array([HEADS[h][0] for h in h_names], float); h_w /= h_w.sum()
    stations = {d: [f"{d} {n}" for n in ("City PS", "North PS", "South PS", "Rural PS", "Cyber PS")] for d in d_names}
    officers = {d: [f"{random.choice(RANKS)} {fake.name()}" for _ in range(8)] for d in d_names}

    # Continue FIR serials per district from the max already used in `cases`,
    # so newly minted numbers never collide with the base file's ids.
    counters: dict[str, int] = {}
    for fir, d in zip(cases["FIR Number"], cases["District"]):
        try:
            serial = int(str(fir).rsplit("/", 1)[-1])
        except ValueError:
            continue
        counters[d] = max(counters.get(d, 0), serial)

    update_start = END + dt.timedelta(days=1)
    update_end = END + dt.timedelta(days=21)  # 3 weeks after END

    def _update_ts(peak_hours):
        base = update_start + dt.timedelta(days=int(rng.integers(0, (update_end - update_start).days + 1)))
        hour = int(rng.choice(peak_hours)) if rng.random() < 0.55 else int(rng.integers(0, 24))
        return base.replace(hour=hour, minute=int(rng.integers(0, 60)), second=0, microsecond=0)

    def one(d, head, ts):
        sub = random.choice(HEADS[head][3])
        lat, lng = DISTRICTS[d][0], DISTRICTS[d][1]
        counters[d] = counters.get(d, 0) + 1
        firno = f"{DISTRICTS[d][3]}/{ts.year}/{counters[d]:05d}"
        status, _, report = random.choices(
            STATUS_REPORT, [w for _, w, _ in STATUS_REPORT])[0]
        cat = "UDR" if head == "Missing Persons" and rng.random() < 0.5 else (
            "Zero FIR" if rng.random() < 0.03 else "FIR")
        return {
            "FIR Number": firno,
            "Crime Registered Date": (ts + dt.timedelta(hours=float(rng.exponential(14)))).date(),
            "District": d,
            "Police Station": random.choice(stations[d]),
            "Case Category": cat,
            "Gravity of Offence": "Heinous" if sub in HEINOUS else "Non-Heinous",
            "Crime Major Head": head,
            "Crime Minor Head": sub,
            "Acts and Sections": SECTIONS.get(sub, "IPC 379"),
            "Case Status": status,
            "Final Report Type": report,
            "Court": f"{d} JMFC Court",
            "Investigating Officer": random.choice(officers[d]),
            "Incident Date Time": ts,
            "Info Received Date": (ts + dt.timedelta(hours=float(rng.exponential(14)))).date(),
            "Latitude": round(lat + rng.normal(0, 0.05), 6),
            "Longitude": round(lng + rng.normal(0, 0.05), 6),
            "Brief Facts": f"{sub} reported under {head} at {d}.",
        }

    new_recs = []
    for _ in range(n_new):
        d = str(rng.choice(d_names, p=d_w)); head = str(rng.choice(h_names, p=h_w))
        new_recs.append(one(d, head, _update_ts(HEADS[head][1])))
    new_rows = pd.DataFrame(new_recs)

    # Duplicate-FIR dedupe demo: rows copied verbatim (identical FIR Number) from
    # the base cases frame — `append_tables` dedupes by the ID-role column, so
    # these should all land as `duplicates_skipped`, not `added`.
    dupe_rows = cases.sample(n=min(n_dupe, len(cases)), random_state=23).copy()

    update = pd.concat([new_rows, dupe_rows], ignore_index=True).sample(frac=1, random_state=29).reset_index(drop=True)
    return update


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=25000,
                    help="incident rows (live-upload safe to ~30-40k; go bigger for a LOCAL demo)")
    ap.add_argument("--append-month", action="store_true",
                    help="also write samples/excel-silos/append/Crime_Cases_Update.xlsx "
                         "(monthly-append demo prop: new rows after END + verbatim dupes)")
    args = ap.parse_args()
    cases, accused, victims, complainants = build(args.rows)
    out = (Path(__file__).resolve().parents[3] / "samples" / "excel-silos")
    out.mkdir(parents=True, exist_ok=True)
    cases.to_excel(out / "Crime_Cases.xlsx", index=False)
    accused.to_excel(out / "Accused.xlsx", index=False)
    victims.to_excel(out / "Victims.xlsx", index=False)
    complainants.to_excel(out / "Complainants.xlsx", index=False)
    print(f"Wrote to {out}:")
    for nm, df in [("Crime_Cases", cases), ("Accused", accused),
                   ("Victims", victims), ("Complainants", complainants)]:
        print(f"  {nm:13}.xlsx : {len(df):>5} rows, {len(df.columns)} cols")

    if args.append_month:
        update = build_append_month(cases)
        append_dir = out / "append"
        append_dir.mkdir(parents=True, exist_ok=True)
        update.to_excel(append_dir / "Crime_Cases_Update.xlsx", index=False)
        n_new = (update["FIR Number"].isin(cases["FIR Number"])).eq(False).sum()
        n_dupe = len(update) - n_new
        print(f"Wrote to {append_dir}:")
        print(f"  Crime_Cases_Update.xlsx : {len(update):>5} rows "
              f"({n_new} new, {n_dupe} verbatim dupes of base FIRs), {len(update.columns)} cols")


if __name__ == "__main__":
    main()
