"""Synthetic KSP FIR data generator — official 28-table normalized schema.

Faithfully models the Karnataka Police FIR ER diagram with integer FK IDs and
lookup master tables. Five planted investigation patterns are re-expressed on
the normalized schema so the demo can "discover" them through DRISHTI.

Planted patterns:
  1. Serial burglary ring: 8 accused sharing phones across 3 districts, ~60
     night-time Burglary CaseMaster rows.
  2. Cybercrime spike in Bengaluru City over the final 5 weeks.
  3. Migrating theft hotspot: lat/long shifts by quarter in Bengaluru City.
  4. Money-mule network: 5 kingpin UPI handles across ~40 cyber cases in 5
     districts (only shared UpiId links otherwise-local mules).
  5. Alias identities: same offender booked under name variants for fuzzy
     entity resolution.

Usage:
    DATA_DIR=/path/to/data PYTHONPATH=. python scripts/generate_fir_data.py --rows 200000
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from faker import Faker

# ------------------------------------------------------------------ CONFIG

END = dt.datetime(2026, 5, 31)
START = END - dt.timedelta(days=3 * 365)

DISTRICTS = {  # name: (lat, lng, weight)
    "Bengaluru City":    (12.9716, 77.5946, 30),
    "Bengaluru Rural":   (13.2846, 77.6190,  5),
    "Mysuru":            (12.2958, 76.6394,  8),
    "Mangaluru City":    (12.8703, 74.8420,  6),
    "Belagavi":          (15.8497, 74.4977,  6),
    "Hubballi-Dharwad":  (15.3647, 75.1240,  6),
    "Kalaburagi":        (17.3297, 76.8343,  5),
    "Ballari":           (15.1394, 76.9214,  4),
    "Shivamogga":        (13.9299, 75.5681,  4),
    "Tumakuru":          (13.3392, 77.1010,  5),
    "Davanagere":        (14.4644, 75.9218,  4),
    "Vijayapura":        (16.8302, 75.7100,  3),
    "Hassan":            (13.0068, 76.0996,  3),
    "Udupi":             (13.3409, 74.7421,  3),
    "Raichur":           (16.2076, 77.3563,  3),
}

STATIONS_PER_DISTRICT = 6

DEMOGRAPHICS = {
    "Bengaluru City":   (9_600_000,  786,  100.0, 88.7),
    "Bengaluru Rural":  (  990_000, 2298,   27.1, 77.9),
    "Mysuru":           (3_001_000, 6307,   41.5, 72.8),
    "Mangaluru City":   (  620_000,  184,  100.0, 94.0),
    "Belagavi":         (4_779_000,13415,   25.3, 73.5),
    "Hubballi-Dharwad": (1_050_000,  213,  100.0, 87.0),
    "Kalaburagi":       (2_566_000,10951,   32.6, 64.9),
    "Ballari":          (2_452_000, 8450,   37.5, 67.4),
    "Shivamogga":       (1_752_000, 8477,   35.6, 80.4),
    "Tumakuru":         (2_678_000,10597,   22.4, 75.1),
    "Davanagere":       (1_946_000, 5924,   32.3, 75.7),
    "Vijayapura":       (2_177_000,10494,   23.2, 67.2),
    "Hassan":           (1_776_000, 6814,   21.2, 76.1),
    "Udupi":            (1_177_000, 3880,   28.4, 86.2),
    "Raichur":          (1_929_000, 8440,   25.4, 59.6),
}

# crime_group: (weight, [peak hours], avg property loss or 0)
CRIME_GROUPS = {
    "Theft":             (22, [10, 14, 19], 25000),
    "Vehicle Theft":     (10, [21, 23,  2], 80000),
    "Burglary":          ( 9, [ 1,  2,  3], 120000),
    "Robbery":           ( 5, [20, 22, 23], 60000),
    "Assault":           (12, [18, 20, 22], 0),
    "Cybercrime":        (10, [11, 15, 17], 150000),
    "Fraud & Cheating":  ( 9, [11, 14, 16], 300000),
    "Murder":            ( 1, [22,  0,  2], 0),
    "Missing Person":    ( 6, [ 8, 12, 18], 0),
    "Narcotics":         ( 4, [21, 23,  1], 0),
    "Sexual Offences":   ( 4, [20, 22,  0], 0),
    "Rioting":           ( 3, [16, 18, 20], 0),
    "Domestic Violence": ( 5, [20, 21, 22], 0),
}

CRIME_HEADS = {
    "Theft":             ["Pickpocketing", "Chain Snatching", "Mobile Theft", "Shop Theft"],
    "Vehicle Theft":     ["Two-Wheeler Theft", "Car Theft", "Auto Theft"],
    "Burglary":          ["House Break-in (Night)", "House Break-in (Day)", "Shop Break-in"],
    "Robbery":           ["Street Robbery", "Highway Robbery", "Dacoity"],
    "Assault":           ["Simple Hurt", "Grievous Hurt", "Affray"],
    "Cybercrime":        ["UPI Fraud", "OTP Scam", "Investment App Fraud", "Sextortion", "Job Fraud"],
    "Fraud & Cheating":  ["Cheating", "Forgery", "Chit Fund Fraud", "Land Fraud"],
    "Murder":            ["Murder", "Attempt to Murder"],
    "Missing Person":    ["Missing Adult", "Missing Minor"],
    "Narcotics":         ["NDPS Possession", "NDPS Peddling"],
    "Sexual Offences":   ["Harassment", "POCSO", "Assault on Woman"],
    "Rioting":           ["Unlawful Assembly", "Rioting"],
    "Domestic Violence": ["498A Cruelty", "Dowry Harassment"],
}

MONTH_FACTOR = [0.95, 0.92, 1.0, 1.05, 1.1, 1.0, 0.98, 1.0, 1.02, 1.08, 1.05, 1.12]

# ---- Detection-outcome model (case status is NOT random — it's a learnable,
# non-leaked function of case features) ----------------------------------
# `has_lead`: latent Bernoulli flag per case ~ P(crime type) — crimes with a
# known victim/assailant relationship (assault, domestic violence, murder)
# have a high prior probability of a lead; anonymous/opportunistic crimes
# (cybercrime, theft, burglary) have a low one. This ALSO drives whether an
# Accused row gets generated (see build()), so `n_accused>0` correlates with
# — but never perfectly determines — the detection outcome.
HAS_LEAD_P = {
    "Domestic Violence": 0.80,
    "Assault":           0.75,
    "Murder":            0.65,
    "Rioting":           0.60,
    "Sexual Offences":   0.55,
    "Narcotics":         0.50,
    "Missing Person":    0.45,
    "Robbery":           0.40,
    "Fraud & Cheating":  0.20,
    "Theft":             0.20,
    "Vehicle Theft":     0.15,
    "Burglary":          0.15,
    "Cybercrime":        0.10,
}
# per-crime-type detection-logit offset (b_type): independent of has_lead,
# some crime types are just easier/harder to close (e.g. narcotics = usually
# caught in the act; cybercrime = jurisdictionally hard even with a lead).
# Values tuned (x3 vs. a first-pass draft) via
# .superpowers/sdd/ml-realism-report.md's sweep to land ksp-fir's detection
# AUC in the target [0.72, 0.90] band without any single feature dominating
# (crime_type and report_delay_h end up the two strongest, comparably sized).
_TYPE_LOGIT_SCALE = 3.0
DETECTION_TYPE_LOGIT = {k: v * _TYPE_LOGIT_SCALE for k, v in {
    "Narcotics":         0.55,
    "Domestic Violence": 0.35,
    "Assault":           0.30,
    "Rioting":           0.25,
    "Murder":            0.15,
    "Missing Person":    0.05,
    "Robbery":           0.00,
    "Sexual Offences":  -0.05,
    "Theft":            -0.15,
    "Vehicle Theft":    -0.20,
    "Fraud & Cheating": -0.30,
    "Burglary":         -0.35,
    "Cybercrime":       -0.55,
}.items()}
DET_B0 = 0.35          # baseline logit (~0.59 detected-if-average, tuned down by other terms)
DET_B_GRAVITY = -0.60  # heinous cases are harder/slower to close
DET_B_LEAD = 3.2       # a lead is a strong driver (partially recoverable via crime_type)
DET_B_DELAY = 1.0      # per z-scored report-delay unit, later reporting hurts detection
DET_SIGMA = 0.4        # Normal(0, sigma) noise so no feature combo is deterministic


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


ANALYTICS_VIEW_SQL = '''
SELECT
  cm."CaseMasterID"        AS case_id,
  cm."CrimeNo"             AS fir_no,
  cm."CrimeRegisteredDate" AS registered_date,
  io."IncidentFromDate"    AS occurrence_ts,
  io."InfoReceivedPSDate"  AS reported_ts,
  io."latitude"            AS latitude,
  io."longitude"           AS longitude,
  io."BriefFacts"          AS brief_facts,
  u."UnitName"             AS police_station,
  u."DistrictName"         AS district,
  ch."CrimeGroupName"      AS crime_major_head,
  csh."CrimeHeadName"      AS crime_minor_head,
  cat."LookupValue"        AS case_category,
  grav."LookupValue"       AS gravity,
  cs."CaseStatusName"      AS case_status,
  crt."CourtName"          AS court
FROM "CaseMaster" cm
LEFT JOIN "Inv_OccuranceTime" io ON io."CaseMasterID"   = cm."CaseMasterID"
LEFT JOIN "Unit" u               ON u."UnitID"          = cm."PoliceStationID"
LEFT JOIN "CaseCategory" cat     ON cat."CaseCategoryID"= cm."CaseCategoryID"
LEFT JOIN "GravityOffence" grav  ON grav."GravityOffenceID" = cm."GravityOffenceID"
LEFT JOIN "CrimeHead" ch         ON ch."CrimeHeadID"    = cm."CrimeMajorHeadID"
LEFT JOIN "CrimeSubHead" csh     ON csh."CrimeSubHeadID"= cm."CrimeMinorHeadID"
LEFT JOIN "CaseStatusMaster" cs  ON cs."CaseStatusID"   = cm."CaseStatusID"
LEFT JOIN "Court" crt            ON crt."CourtID"       = cm."CourtID"
'''.strip()

# -------------------------------------------------------- SEEDED RNG

rng = np.random.default_rng(42)
random.seed(42)
fake = Faker("en_IN")
Faker.seed(42)


# -------------------------------------------------------- HELPERS

def _sample_time(n: int, peak_hours: list[int]) -> list[dt.datetime]:
    days = (END - START).days
    weights = np.array([
        MONTH_FACTOR[(START + dt.timedelta(days=int(x))).month - 1]
        for x in range(days)
    ])
    weights /= weights.sum()
    day_idx = rng.choice(days, size=n, p=weights)
    out = []
    for di in day_idx:
        base = START + dt.timedelta(days=int(di))
        hour = int(rng.choice(peak_hours)) if rng.random() < 0.55 else int(rng.integers(0, 24))
        out.append(base.replace(hour=hour, minute=int(rng.integers(0, 60))))
    return out


def _crime_no(cat_code: str, district_id: int, ps_id: int, year: int, serial: int) -> str:
    return f"{cat_code}{district_id:04d}{ps_id:04d}{year}{serial:05d}"


# -------------------------------------------------------- BUILD MASTERS

def _build_state() -> pd.DataFrame:
    rows = [
        {"StateID": 1, "StateName": "Karnataka", "NationalityID": 1, "Active": True},
        {"StateID": 2, "StateName": "Tamil Nadu", "NationalityID": 1, "Active": True},
        {"StateID": 3, "StateName": "Andhra Pradesh", "NationalityID": 1, "Active": True},
        {"StateID": 4, "StateName": "Telangana", "NationalityID": 1, "Active": True},
        {"StateID": 5, "StateName": "Goa", "NationalityID": 1, "Active": True},
    ]
    return pd.DataFrame(rows)


def _build_district() -> tuple[pd.DataFrame, dict[str, int]]:
    rows = []
    name_to_id: dict[str, int] = {}
    for i, d_name in enumerate(DISTRICTS, start=1):
        rows.append({"DistrictID": i, "DistrictName": d_name, "StateID": 1, "Active": True})
        name_to_id[d_name] = i
    return pd.DataFrame(rows), name_to_id


def _build_unit_type() -> pd.DataFrame:
    rows = [
        {"UnitTypeID": 1, "UnitTypeName": "Police Station", "CityDistState": "D", "Hierarchy": 1, "Active": True},
        {"UnitTypeID": 2, "UnitTypeName": "Circle",         "CityDistState": "D", "Hierarchy": 2, "Active": True},
        {"UnitTypeID": 3, "UnitTypeName": "Sub-Division",   "CityDistState": "D", "Hierarchy": 3, "Active": True},
        {"UnitTypeID": 4, "UnitTypeName": "District HQ",    "CityDistState": "D", "Hierarchy": 4, "Active": True},
    ]
    return pd.DataFrame(rows)


def _build_unit(
    district_df: pd.DataFrame,
    dist_name_to_id: dict[str, int],
) -> tuple[pd.DataFrame, dict[str, dict[str, object]]]:
    """Returns (Unit df, stations dict: dist_name -> list of {UnitID, lat, lng, UnitName})"""
    rows = []
    unit_id = 1
    stations: dict[str, list[dict]] = {}
    for d_name, (lat, lng, _) in DISTRICTS.items():
        d_id = dist_name_to_id[d_name]
        d_stations = []
        for i in range(STATIONS_PER_DISTRICT):
            slat = lat + rng.normal(0, 0.06)
            slng = lng + rng.normal(0, 0.06)
            unit_name = f"{d_name} PS-{i + 1}"
            rows.append({
                "UnitID": unit_id,
                "UnitName": unit_name,
                "TypeID": 1,
                "ParentUnit": None,
                "NationalityID": 1,
                "StateID": 1,
                "DistrictID": d_id,
                "Active": True,
                "DistrictName": d_name,   # enrichment
                "StateName": "Karnataka", # enrichment
            })
            d_stations.append({"UnitID": unit_id, "UnitName": unit_name, "lat": float(slat), "lng": float(slng)})
            unit_id += 1
        stations[d_name] = d_stations
    return pd.DataFrame(rows), stations


def _build_rank() -> pd.DataFrame:
    ranks = [
        ("Constable", 1), ("Head Constable", 2), ("ASI", 3),
        ("SI", 4), ("PSI", 5), ("PI", 6), ("DySP", 7), ("SP", 8),
    ]
    return pd.DataFrame([
        {"RankID": i + 1, "RankName": name, "Hierarchy": h, "Active": True}
        for i, (name, h) in enumerate(ranks)
    ])


def _build_designation() -> pd.DataFrame:
    desigs = [("IO", 1), ("SHO", 2), ("Writer", 3), ("DC", 4)]
    return pd.DataFrame([
        {"DesignationID": i + 1, "DesignationName": name, "Active": True, "SortOrder": order}
        for i, (name, order) in enumerate(desigs)
    ])


def _build_employee(
    dist_name_to_id: dict[str, int],
    stations: dict[str, list[dict]],
    n: int = 500,
) -> pd.DataFrame:
    d_names = list(DISTRICTS)
    d_weights = np.array([w for _, _, w in DISTRICTS.values()], dtype=float)
    d_weights /= d_weights.sum()
    blood_groups = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]
    rows = []
    for i in range(n):
        d_name = str(rng.choice(d_names, p=d_weights))
        unit = random.choice(stations[d_name])
        rows.append({
            "EmployeeID": i + 1,
            "DistrictID": dist_name_to_id[d_name],
            "UnitID": unit["UnitID"],
            "RankID": int(rng.integers(1, 9)),
            "DesignationID": int(rng.integers(1, 5)),
            "KGID": f"KG{i + 1:06d}",
            "FirstName": fake.first_name(),
            "EmployeeDOB": str(dt.date(int(rng.integers(1960, 1995)), int(rng.integers(1, 13)), int(rng.integers(1, 28)))),
            "GenderID": str(rng.choice(["M", "F"], p=[0.85, 0.15])),
            "BloodGroupID": str(rng.choice(blood_groups)),
            "PhysicallyChallenged": bool(rng.random() < 0.02),
            "AppointmentDate": str(dt.date(int(rng.integers(1990, 2020)), int(rng.integers(1, 13)), int(rng.integers(1, 28)))),
        })
    return pd.DataFrame(rows)


def _build_case_category() -> tuple[pd.DataFrame, dict[str, int]]:
    cats = [("FIR", "F"), ("UDR", "U"), ("Zero FIR", "Z"), ("PAR", "P")]
    rows = []
    name_to_id: dict[str, int] = {}
    for i, (name, code) in enumerate(cats, start=1):
        rows.append({"CaseCategoryID": i, "LookupValue": name})
        name_to_id[name] = i
        name_to_id[code] = i
    return pd.DataFrame(rows), name_to_id


def _build_gravity() -> tuple[pd.DataFrame, dict[str, int]]:
    gravs = ["Heinous", "Non-Heinous"]
    rows = [{"GravityOffenceID": i + 1, "LookupValue": g} for i, g in enumerate(gravs)]
    name_to_id = {g: i + 1 for i, g in enumerate(gravs)}
    return pd.DataFrame(rows), name_to_id


def _build_crime_head() -> tuple[pd.DataFrame, dict[str, int]]:
    rows = []
    name_to_id: dict[str, int] = {}
    for i, group_name in enumerate(CRIME_GROUPS, start=1):
        rows.append({"CrimeHeadID": i, "CrimeGroupName": group_name, "Active": True})
        name_to_id[group_name] = i
    return pd.DataFrame(rows), name_to_id


def _build_crime_sub_head(crime_head_name_to_id: dict[str, int]) -> tuple[pd.DataFrame, dict[str, int]]:
    rows = []
    name_to_id: dict[str, int] = {}
    sub_id = 1
    for group_name, sub_names in CRIME_HEADS.items():
        head_id = crime_head_name_to_id[group_name]
        for seq, sub_name in enumerate(sub_names, start=1):
            rows.append({
                "CrimeSubHeadID": sub_id,
                "CrimeHeadID": head_id,
                "CrimeHeadName": sub_name,
                "SeqID": seq,
            })
            name_to_id[sub_name] = sub_id
            sub_id += 1
    return pd.DataFrame(rows), name_to_id


def _build_case_status() -> tuple[pd.DataFrame, dict[str, int]]:
    statuses = [
        "Under Investigation", "Charge Sheeted", "Closed", "Convicted", "Acquitted"
    ]
    rows = [{"CaseStatusID": i + 1, "CaseStatusName": s} for i, s in enumerate(statuses)]
    name_to_id = {s: i + 1 for i, s in enumerate(statuses)}
    return pd.DataFrame(rows), name_to_id


def _build_court(dist_name_to_id: dict[str, int]) -> tuple[pd.DataFrame, dict[int, list[int]]]:
    """Returns (Court df, dist_id -> [CourtID] map)."""
    rows = []
    court_id = 1
    dist_to_courts: dict[int, list[int]] = {}
    court_types = ["District Court", "Magistrate Court", "Sessions Court"]
    for d_name, d_id in dist_name_to_id.items():
        n_courts = 2
        cids = []
        for k in range(n_courts):
            rows.append({
                "CourtID": court_id,
                "CourtName": f"{d_name} {court_types[k % len(court_types)]}",
                "DistrictID": d_id,
                "StateID": 1,
                "Active": True,
            })
            cids.append(court_id)
            court_id += 1
        dist_to_courts[d_id] = cids
    return pd.DataFrame(rows), dist_to_courts


def _build_act() -> tuple[pd.DataFrame, list[str]]:
    rows = [
        {"ActCode": "IPC",   "ActDescription": "Indian Penal Code",              "ShortName": "IPC",   "Active": True},
        {"ActCode": "BNS",   "ActDescription": "Bharatiya Nyaya Sanhita",         "ShortName": "BNS",   "Active": True},
        {"ActCode": "NDPS",  "ActDescription": "Narcotic Drugs & Psychotropic Substances Act", "ShortName": "NDPS",  "Active": True},
        {"ActCode": "IT",    "ActDescription": "Information Technology Act",       "ShortName": "IT Act","Active": True},
        {"ActCode": "POCSO", "ActDescription": "Protection of Children from Sexual Offences Act", "ShortName": "POCSO", "Active": True},
    ]
    return pd.DataFrame(rows), [r["ActCode"] for r in rows]


def _build_section() -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    rows = [
        {"ActCode": "IPC",   "SectionCode": "302", "SectionDescription": "Murder",                         "Active": True},
        {"ActCode": "IPC",   "SectionCode": "379", "SectionDescription": "Theft",                          "Active": True},
        {"ActCode": "IPC",   "SectionCode": "380", "SectionDescription": "Theft in dwelling house",         "Active": True},
        {"ActCode": "IPC",   "SectionCode": "392", "SectionDescription": "Robbery",                        "Active": True},
        {"ActCode": "IPC",   "SectionCode": "420", "SectionDescription": "Cheating",                       "Active": True},
        {"ActCode": "IPC",   "SectionCode": "498A","SectionDescription": "Cruelty by husband",             "Active": True},
        {"ActCode": "BNS",   "SectionCode": "103", "SectionDescription": "Murder (BNS)",                   "Active": True},
        {"ActCode": "BNS",   "SectionCode": "303", "SectionDescription": "Theft (BNS)",                    "Active": True},
        {"ActCode": "NDPS",  "SectionCode": "8C",  "SectionDescription": "Possession of drugs",            "Active": True},
        {"ActCode": "NDPS",  "SectionCode": "20B", "SectionDescription": "Peddling drugs",                 "Active": True},
        {"ActCode": "IT",    "SectionCode": "66C", "SectionDescription": "Identity theft",                 "Active": True},
        {"ActCode": "IT",    "SectionCode": "66D", "SectionDescription": "Cheating by personation",        "Active": True},
        {"ActCode": "POCSO", "SectionCode": "4",   "SectionDescription": "Penetrative sexual assault",     "Active": True},
        {"ActCode": "POCSO", "SectionCode": "8",   "SectionDescription": "Sexual assault",                 "Active": True},
    ]
    pairs = [(r["ActCode"], r["SectionCode"]) for r in rows]
    return pd.DataFrame(rows), pairs


def _build_crime_head_act_section(
    crime_head_name_to_id: dict[str, int],
    act_section_pairs: list[tuple[str, str]],
) -> pd.DataFrame:
    # Simple mapping: each crime head gets 1-2 sections
    mapping = {
        "Murder":            [("IPC", "302"), ("BNS", "103")],
        "Theft":             [("IPC", "379"), ("BNS", "303")],
        "Burglary":          [("IPC", "380")],
        "Robbery":           [("IPC", "392")],
        "Fraud & Cheating":  [("IPC", "420")],
        "Domestic Violence": [("IPC", "498A")],
        "Narcotics":         [("NDPS", "8C"), ("NDPS", "20B")],
        "Cybercrime":        [("IT", "66C"), ("IT", "66D")],
        "Sexual Offences":   [("POCSO", "4"), ("POCSO", "8")],
    }
    valid_pairs = set(act_section_pairs)
    rows = []
    for group_name, sections in mapping.items():
        head_id = crime_head_name_to_id.get(group_name)
        if head_id is None:
            continue
        for act_code, sec_code in sections:
            if (act_code, sec_code) in valid_pairs:
                rows.append({"CrimeHeadID": head_id, "ActCode": act_code, "SectionCode": sec_code})
    return pd.DataFrame(rows)


def _build_caste() -> tuple[pd.DataFrame, list[int]]:
    castes = ["General", "OBC", "SC", "ST", "Other"]
    rows = [{"caste_master_id": i + 1, "caste_master_name": c} for i, c in enumerate(castes)]
    return pd.DataFrame(rows), [r["caste_master_id"] for r in rows]


def _build_religion() -> tuple[pd.DataFrame, list[int]]:
    religions = ["Hindu", "Muslim", "Christian", "Other"]
    rows = [{"ReligionID": i + 1, "ReligionName": r} for i, r in enumerate(religions)]
    return pd.DataFrame(rows), [r["ReligionID"] for r in rows]


def _build_occupation() -> tuple[pd.DataFrame, list[int]]:
    occs = ["Farmer", "Labourer", "Business", "Student", "Driver", "Unemployed", "Other"]
    rows = [{"OccupationID": i + 1, "OccupationName": o} for i, o in enumerate(occs)]
    return pd.DataFrame(rows), [r["OccupationID"] for r in rows]


# -------------------------------------------------------- BUILD FACTS

def build(rows: int = 200000) -> dict[str, pd.DataFrame]:
    """Build all 28 tables as DataFrames. Keys are the exact schema names."""

    # Re-seed for reproducibility regardless of call order
    global rng
    rng = np.random.default_rng(42)
    random.seed(42)
    Faker.seed(42)

    # ---- Masters ----
    state_df = _build_state()
    district_df, dist_name_to_id = _build_district()
    unit_type_df = _build_unit_type()
    unit_df, stations = _build_unit(district_df, dist_name_to_id)
    rank_df = _build_rank()
    designation_df = _build_designation()
    employee_df = _build_employee(dist_name_to_id, stations)

    case_category_df, cat_name_to_id = _build_case_category()
    gravity_df, grav_name_to_id = _build_gravity()
    crime_head_df, ch_name_to_id = _build_crime_head()
    crime_sub_head_df, csh_name_to_id = _build_crime_sub_head(ch_name_to_id)
    case_status_df, status_name_to_id = _build_case_status()
    court_df, dist_to_courts = _build_court(dist_name_to_id)
    act_df, act_codes = _build_act()
    section_df, act_section_pairs = _build_section()
    crime_head_act_section_df = _build_crime_head_act_section(ch_name_to_id, act_section_pairs)
    caste_df, caste_ids = _build_caste()
    religion_df, religion_ids = _build_religion()
    occupation_df, occupation_ids = _build_occupation()

    # ---- Fact: CaseMaster ----
    d_names = list(DISTRICTS)
    d_weights = np.array([w for _, _, w in DISTRICTS.values()], dtype=float)
    d_weights /= d_weights.sum()
    g_names = list(CRIME_GROUPS)
    g_weights = np.array([w for w, _, _ in CRIME_GROUPS.values()], dtype=float)
    g_weights /= g_weights.sum()

    n_base = rows
    districts_sampled = [str(x) for x in rng.choice(d_names, size=n_base, p=d_weights)]
    groups_sampled = [str(x) for x in rng.choice(g_names, size=n_base, p=g_weights)]

    # `has_lead`: latent per-case Bernoulli flag (see HAS_LEAD_P) — NOT persisted
    # to the schema, used only to drive detection probability + Accused
    # generation below, so it can never leak into ml.py (which reads real
    # manifest columns by semantic role, and this never becomes one).
    lead_p_vec = np.array([HAS_LEAD_P[g] for g in groups_sampled])
    has_lead_sampled = rng.random(n_base) < lead_p_vec
    # report-delay z-score needs a population mean/std; report delay here is
    # ~Exponential(18h) regardless of status (computed per-row below), so we
    # z-score against the exponential's known mean/std (mean=std=18) rather
    # than a second pass over the data.
    REPORT_DELAY_MEAN_H = 18.0
    REPORT_DELAY_STD_H = 18.0
    noise_vec = rng.normal(0, DET_SIGMA, n_base)

    # Build fact records
    case_rows = []
    occurrence_rows = []
    case_serial: dict[tuple, int] = {}  # (cat_code, dist_id, ps_id, year) -> serial
    grievous_groups = {"Murder", "Robbery", "Sexual Offences", "Narcotics"}
    # Category weights: mostly FIR
    cat_choices = [1, 2, 3, 4]  # FIR=1, UDR=2, ZeroFIR=3, PAR=4
    cat_weights = [0.75, 0.10, 0.10, 0.05]
    cat_codes = {1: "F", 2: "U", 3: "Z", 4: "P"}

    employee_ids = list(employee_df["EmployeeID"])
    has_lead_by_case: dict[int, bool] = {}  # CaseMasterID -> has_lead, for Accused gen below

    for i in range(n_base):
        d_name = districts_sampled[i]
        grp = groups_sampled[i]
        station = random.choice(stations[d_name])
        ts = _sample_time(1, CRIME_GROUPS[grp][1])[0]

        # Pattern 3: migrating theft hotspot (Bengaluru City, by quarter)
        st_lat, st_lng = station["lat"], station["lng"]
        if d_name == "Bengaluru City" and grp == "Theft" and rng.random() < 0.35:
            quarter = (ts.month - 1) // 3
            centers = [(12.935, 77.61), (12.98, 77.64), (13.01, 77.555), (12.91, 77.50)]
            st_lat, st_lng = centers[quarter]

        lat = st_lat + rng.normal(0, 0.015)
        lng = st_lng + rng.normal(0, 0.015)

        d_id = dist_name_to_id[d_name]
        ps_id = station["UnitID"]
        cat_id = int(rng.choice(cat_choices, p=cat_weights))
        cat_code = cat_codes[cat_id]
        year = ts.year
        key = (cat_code, d_id, ps_id, year)
        case_serial[key] = case_serial.get(key, 0) + 1
        crime_no = _crime_no(cat_code, d_id, ps_id, year, case_serial[key])

        is_heinous = grp in grievous_groups
        grav_id = grav_name_to_id["Heinous"] if is_heinous else grav_name_to_id["Non-Heinous"]
        sub_head = random.choice(CRIME_HEADS[grp])
        sub_head_id = csh_name_to_id[sub_head]
        head_id = ch_name_to_id[grp]

        io_id = int(rng.choice(employee_ids))
        reg_date = ts + dt.timedelta(hours=float(rng.exponential(18)))
        report_delay_h = float(rng.exponential(18))
        reported_ts = ts + dt.timedelta(hours=report_delay_h)

        # ---- realistic, learnable, non-leaked detection outcome ----
        has_lead = bool(has_lead_sampled[i])
        delay_z = (report_delay_h - REPORT_DELAY_MEAN_H) / REPORT_DELAY_STD_H
        logit = (
            DET_B0
            + DETECTION_TYPE_LOGIT[grp]
            + (DET_B_GRAVITY if is_heinous else 0.0)
            + (DET_B_LEAD if has_lead else 0.0)
            - DET_B_DELAY * delay_z
            + float(noise_vec[i])
        )
        p_detect = float(_sigmoid(np.array([logit]))[0])
        detected = rng.random() < p_detect

        days_since_reg = (END - reg_date).days
        if detected:
            status_name = str(rng.choice(
                ["Charge Sheeted", "Convicted", "Acquitted"], p=[0.55, 0.28, 0.17]))
        else:
            # recent cases are still being worked; older undetected cases close.
            p_still_open = float(np.clip(1.0 - days_since_reg / 240.0, 0.05, 0.92))
            status_name = "Under Investigation" if rng.random() < p_still_open else "Closed"
        status_id = status_name_to_id[status_name]

        court_ids_for_dist = dist_to_courts[d_id]
        court_id = int(rng.choice(court_ids_for_dist)) if status_name in ("Convicted", "Acquitted", "Charge Sheeted") else None

        has_lead_by_case[i + 1] = has_lead

        brief = f"{sub_head} reported at {station['UnitName']}"

        case_rows.append({
            "CaseMasterID": i + 1,
            "CrimeNo": crime_no,
            "CaseNo": f"{d_id:04d}/{year}/{case_serial[key]:05d}",
            "CrimeRegisteredDate": reg_date,
            "PolicePersonID": io_id,
            "PoliceStationID": ps_id,
            "CaseCategoryID": cat_id,
            "GravityOffenceID": grav_id,
            "CrimeMajorHeadID": head_id,
            "CrimeMinorHeadID": sub_head_id,
            "CaseStatusID": status_id,
            "CourtID": court_id,
            "_d_name": d_name,          # temp column for joining pattern rows
            "_grp": grp,
            "_status": status_name,
            "_ts": ts,
        })
        occurrence_rows.append({
            "CaseMasterID": i + 1,
            "IncidentFromDate": ts,
            "IncidentToDate": ts + dt.timedelta(hours=float(rng.integers(1, 4))),
            "InfoReceivedPSDate": reported_ts,
            "latitude": round(float(lat), 6),
            "longitude": round(float(lng), 6),
            "BriefFacts": brief,
        })

    # ---- Pattern 2: Cybercrime spike last 5 weeks (Bengaluru City) ----
    spike_n = max(int(n_base * 0.006), 100)
    grp = "Cybercrime"
    for _ in range(spike_n):
        ts = END - dt.timedelta(days=float(rng.integers(0, 35)),
                                hours=float(rng.integers(0, 24)))
        station = random.choice(stations["Bengaluru City"])
        i_new = len(case_rows) + 1
        d_id = dist_name_to_id["Bengaluru City"]
        ps_id = station["UnitID"]
        cat_id = 1
        cat_code = "F"
        year = ts.year
        key = (cat_code, d_id, ps_id, year)
        case_serial[key] = case_serial.get(key, 0) + 1
        crime_no = _crime_no(cat_code, d_id, ps_id, year, case_serial[key])
        sub_head = random.choice(["Investment App Fraud", "UPI Fraud"])
        sub_head_id = csh_name_to_id[sub_head]
        head_id = ch_name_to_id[grp]
        grav_id = grav_name_to_id["Non-Heinous"]
        status_name = "Under Investigation"
        status_id = status_name_to_id[status_name]
        court_id_val = None
        io_id = int(rng.choice(employee_ids))
        reg_date = ts + dt.timedelta(hours=float(rng.exponential(18)))
        reported_ts = ts + dt.timedelta(hours=float(rng.integers(1, 5)))
        lat = station["lat"] + rng.normal(0, 0.02)
        lng = station["lng"] + rng.normal(0, 0.02)

        case_rows.append({
            "CaseMasterID": i_new,
            "CrimeNo": crime_no,
            "CaseNo": f"{d_id:04d}/{year}/{case_serial[key]:05d}",
            "CrimeRegisteredDate": reg_date,
            "PolicePersonID": io_id,
            "PoliceStationID": ps_id,
            "CaseCategoryID": cat_id,
            "GravityOffenceID": grav_id,
            "CrimeMajorHeadID": head_id,
            "CrimeMinorHeadID": sub_head_id,
            "CaseStatusID": status_id,
            "CourtID": court_id_val,
            "_d_name": "Bengaluru City",
            "_grp": grp,
            "_status": status_name,
            "_ts": ts,
        })
        occurrence_rows.append({
            "CaseMasterID": i_new,
            "IncidentFromDate": ts,
            "IncidentToDate": ts + dt.timedelta(hours=2),
            "InfoReceivedPSDate": reported_ts,
            "latitude": round(float(lat), 6),
            "longitude": round(float(lng), 6),
            "BriefFacts": f"{sub_head} reported at {station['UnitName']}",
        })

    # ---- Pattern 1: Serial burglary ring ----
    ring_districts = ["Bengaluru City", "Tumakuru", "Mysuru"]
    shared_phones = [f"98860{rng.integers(10000, 99999)}" for _ in range(4)]
    ring_members = []
    upi_banks = ["okhdfc", "okaxis", "ybl", "paytm", "okicici"]
    for i in range(8):
        name = fake.name()
        ring_members.append({
            "AccusedName": name,
            "AgeYear": int(rng.integers(22, 40)),
            "GenderID": "M",
            "Phone": str(shared_phones[i // 2]),  # pairs share a phone — hidden link
            "Address": f"{fake.street_address()}, {ring_districts[i % 3]}",
            "UpiId": None,
        })

    grp = "Burglary"
    ring_case_ids = []
    for j in range(60):
        d_name = ring_districts[j % 3]
        station = random.choice(stations[d_name])
        ts = START + dt.timedelta(
            days=float(rng.integers(60, (END - START).days)),
            hours=float(rng.choice([1, 2, 3]))
        )
        i_new = len(case_rows) + 1
        d_id = dist_name_to_id[d_name]
        ps_id = station["UnitID"]
        cat_id = 1
        cat_code = "F"
        year = ts.year
        key = (cat_code, d_id, ps_id, year)
        case_serial[key] = case_serial.get(key, 0) + 1
        crime_no = _crime_no(cat_code, d_id, ps_id, year, case_serial[key])
        sub_head_id = csh_name_to_id["House Break-in (Night)"]
        head_id = ch_name_to_id[grp]
        grav_id = grav_name_to_id["Non-Heinous"]
        status_name = "Under Investigation"
        status_id = status_name_to_id[status_name]
        io_id = int(rng.choice(employee_ids))
        reg_date = ts + dt.timedelta(hours=8)
        lat = station["lat"] + rng.normal(0, 0.01)
        lng = station["lng"] + rng.normal(0, 0.01)

        case_rows.append({
            "CaseMasterID": i_new,
            "CrimeNo": crime_no,
            "CaseNo": f"{d_id:04d}/{year}/{case_serial[key]:05d}",
            "CrimeRegisteredDate": reg_date,
            "PolicePersonID": io_id,
            "PoliceStationID": ps_id,
            "CaseCategoryID": cat_id,
            "GravityOffenceID": grav_id,
            "CrimeMajorHeadID": head_id,
            "CrimeMinorHeadID": sub_head_id,
            "CaseStatusID": status_id,
            "CourtID": None,
            "_d_name": d_name,
            "_grp": grp,
            "_status": status_name,
            "_ts": ts,
        })
        occurrence_rows.append({
            "CaseMasterID": i_new,
            "IncidentFromDate": ts,
            "IncidentToDate": ts + dt.timedelta(hours=1),
            "InfoReceivedPSDate": ts + dt.timedelta(hours=8),
            "latitude": round(float(lat), 6),
            "longitude": round(float(lng), 6),
            "BriefFacts": "House Break-in (Night) — gas cutter used on locks, CCTV avoided",
        })
        ring_case_ids.append(i_new)

    # ---- Pattern 4: Money-mule network ----
    mule_districts = ["Bengaluru City", "Mangaluru City", "Hubballi-Dharwad", "Kalaburagi", "Mysuru"]
    kingpin_upis = [f"quickreturns{k}@ybl" for k in range(1, 6)]
    mule_members = []
    for i in range(25):
        mule_members.append({
            "AccusedName": fake.name(),
            "AgeYear": int(rng.integers(19, 45)),
            "GenderID": str(rng.choice(["M", "F"], p=[0.7, 0.3])),
            "Phone": f"9{rng.integers(100000000, 999999999)}",
            "Address": f"{fake.street_address()}, {mule_districts[i % 5]}",
            "UpiId": kingpin_upis[i % 5],  # shared kingpin handle
        })

    grp = "Cybercrime"
    mule_case_ids = []
    for j in range(40):
        d_name = mule_districts[j % 5]
        station = random.choice(stations[d_name])
        ts = END - dt.timedelta(days=float(rng.integers(0, 400)),
                                hours=float(rng.integers(0, 24)))
        i_new = len(case_rows) + 1
        d_id = dist_name_to_id[d_name]
        ps_id = station["UnitID"]
        cat_id = 1
        cat_code = "F"
        year = ts.year
        key = (cat_code, d_id, ps_id, year)
        case_serial[key] = case_serial.get(key, 0) + 1
        crime_no = _crime_no(cat_code, d_id, ps_id, year, case_serial[key])
        sub_head = random.choice(["Investment App Fraud", "UPI Fraud"])
        sub_head_id = csh_name_to_id[sub_head]
        head_id = ch_name_to_id[grp]
        grav_id = grav_name_to_id["Non-Heinous"]
        status_name = "Under Investigation"
        status_id = status_name_to_id[status_name]
        io_id = int(rng.choice(employee_ids))
        reg_date = ts + dt.timedelta(hours=float(rng.integers(1, 5)))
        lat = station["lat"] + rng.normal(0, 0.02)
        lng = station["lng"] + rng.normal(0, 0.02)
        mule = random.choice([m for i2, m in enumerate(mule_members) if i2 % 5 == j % 5])

        case_rows.append({
            "CaseMasterID": i_new,
            "CrimeNo": crime_no,
            "CaseNo": f"{d_id:04d}/{year}/{case_serial[key]:05d}",
            "CrimeRegisteredDate": reg_date,
            "PolicePersonID": io_id,
            "PoliceStationID": ps_id,
            "CaseCategoryID": cat_id,
            "GravityOffenceID": grav_id,
            "CrimeMajorHeadID": head_id,
            "CrimeMinorHeadID": sub_head_id,
            "CaseStatusID": status_id,
            "CourtID": None,
            "_d_name": d_name,
            "_grp": grp,
            "_status": status_name,
            "_ts": ts,
        })
        occurrence_rows.append({
            "CaseMasterID": i_new,
            "IncidentFromDate": ts,
            "IncidentToDate": ts + dt.timedelta(hours=2),
            "InfoReceivedPSDate": ts + dt.timedelta(hours=30),
            "latitude": round(float(lat), 6),
            "longitude": round(float(lng), 6),
            "BriefFacts": f"Investment app fraud — victim payout routed via UPI handle {mule['UpiId']}",
        })
        mule_case_ids.append(i_new)

    case_master_df = pd.DataFrame(case_rows)
    # Drop temp columns before writing
    _temp_cols = ["_d_name", "_grp", "_status", "_ts"]

    # ---- Accused ----
    # Use a power-law person pool for base accused
    n_persons = max(len(case_master_df) // 6, 50)
    p_names = [fake.name() for _ in range(n_persons)]
    base_persons = [
        {
            "AccusedName": p_names[i],
            "AgeYear": int(rng.integers(16, 65)),
            "GenderID": str(rng.choice(["M", "F"], p=[0.85, 0.15])),
            "Phone": f"9{rng.integers(100000000, 999999999)}",
            "Address": f"{fake.street_address()}, {rng.choice(d_names, p=d_weights)}",
            "UpiId": (
                f"{p_names[i].split()[0].lower()}.{i}@{random.choice(upi_banks)}"
                if random.random() < 0.65 else None
            ),
        }
        for i in range(n_persons)
    ]
    weights_p = rng.pareto(2.5, n_persons) + 1
    weights_p = np.minimum(weights_p, np.percentile(weights_p, 99.5))
    weights_p /= weights_p.sum()

    # Accused rows are generated for cases with a LEAD (has_lead_by_case),
    # not purely by outcome status — this is what breaks the n_accused/status
    # leak: most has_lead cases got DETECTED (b_lead=+1.35 in the logit), but
    # some has_lead cases are still open (Under Investigation) or even ended
    # undetected (the lead didn't pan out), so n_accused>0 is a strong but
    # IMPERFECT predictor of detection, exactly like real investigations.
    # (Cases with case_ids beyond len(has_lead_by_case) are planted-pattern
    # rows — burglary ring / cyber spike / money-mule — each of which attaches
    # its OWN explicit accused below regardless of this dict.)
    lead_mask = case_master_df["CaseMasterID"].map(
        lambda cid: has_lead_by_case.get(int(cid), False))
    lead_case_ids = list(case_master_df.loc[lead_mask, "CaseMasterID"])
    # kept for the alias-pattern block below, which wants "solved" cases
    # specifically (a convicted/acquitted/chargesheeted alias makes narrative
    # sense); independent of the has_lead-driven Accused generation above.
    solved_mask = case_master_df["_status"].isin(["Charge Sheeted", "Convicted", "Acquitted"])
    solved_case_ids = list(case_master_df.loc[solved_mask, "CaseMasterID"])

    acc_rows = []
    acc_id = 1
    for case_id in lead_case_ids:
        for _ in range(int(rng.choice([1, 1, 1, 2, 2, 3]))):
            p = base_persons[int(rng.choice(n_persons, p=weights_p))]
            acc_rows.append({
                "AccusedMasterID": acc_id,
                "CaseMasterID": case_id,
                "AccusedName": p["AccusedName"],
                "AgeYear": p["AgeYear"],
                "GenderID": p["GenderID"],
                "PersonID": None,
                "Phone": p["Phone"],
                "Address": p["Address"],
                "UpiId": p["UpiId"],
            })
            acc_id += 1

    # Pattern 5: alias identities
    alias_pairs = [
        ("Manjunath Gowda", "Manjunath Gowda B", "Bengaluru City"),
        ("Syed Imran Pasha", "Imran Pasha Syed", "Mysuru"),
        ("Ravi Kumar H", "Ravi Kumar", "Davanagere"),
    ]
    for k, (n1, n2, d_name) in enumerate(alias_pairs):
        age = int(rng.integers(25, 50))
        d_solved = list(case_master_df.loc[
            solved_mask & (case_master_df["_d_name"] == d_name), "CaseMasterID"
        ])
        for v, nm in enumerate((n1, n2)):
            phone = f"9{rng.integers(100000000, 999999999)}"
            addr = f"{fake.street_address()}, {d_name}"
            sample_pool = d_solved if len(d_solved) >= 5 else solved_case_ids
            for case_id in random.sample(sample_pool, k=min(5, len(sample_pool))):
                acc_rows.append({
                    "AccusedMasterID": acc_id,
                    "CaseMasterID": int(case_id),
                    "AccusedName": nm,
                    "AgeYear": age,
                    "GenderID": "M",
                    "PersonID": None,
                    "Phone": phone,
                    "Address": addr,
                    "UpiId": None,
                })
                acc_id += 1

    # Pattern 1 accused: ring members on ring cases
    for j, case_id in enumerate(ring_case_ids):
        for member in random.sample(ring_members, k=2):
            acc_rows.append({
                "AccusedMasterID": acc_id,
                "CaseMasterID": int(case_id),
                "AccusedName": member["AccusedName"],
                "AgeYear": member["AgeYear"],
                "GenderID": member["GenderID"],
                "PersonID": None,
                "Phone": member["Phone"],
                "Address": member["Address"],
                "UpiId": member["UpiId"],
            })
            acc_id += 1

    # Pattern 4 accused: mule members on mule cases
    for j, case_id in enumerate(mule_case_ids):
        mule = random.choice([m for i2, m in enumerate(mule_members) if i2 % 5 == j % 5])
        acc_rows.append({
            "AccusedMasterID": acc_id,
            "CaseMasterID": int(case_id),
            "AccusedName": mule["AccusedName"],
            "AgeYear": mule["AgeYear"],
            "GenderID": mule["GenderID"],
            "PersonID": None,
            "Phone": mule["Phone"],
            "Address": mule["Address"],
            "UpiId": mule["UpiId"],
        })
        acc_id += 1

    accused_df = pd.DataFrame(acc_rows)

    # ---- Victims ----
    vic_rows = []
    sample_case_ids = list(case_master_df.sample(frac=0.7, random_state=7)["CaseMasterID"])
    for k, case_id in enumerate(sample_case_ids):
        vic_rows.append({
            "VictimMasterID": k + 1,
            "CaseMasterID": int(case_id),
            "VictimName": fake.name(),
            "AgeYear": int(rng.integers(12, 80)),
            "GenderID": str(rng.choice(["M", "F"], p=[0.55, 0.45])),
            "VictimPolice": bool(rng.random() < 0.05),
        })
    victim_df = pd.DataFrame(vic_rows)

    # ---- ComplainantDetails ----
    comp_rows = []
    sample_comp_ids = list(case_master_df.sample(frac=0.85, random_state=11)["CaseMasterID"])
    for k, case_id in enumerate(sample_comp_ids):
        comp_rows.append({
            "ComplainantID": k + 1,
            "CaseMasterID": int(case_id),
            "ComplainantName": fake.name(),
            "AgeYear": int(rng.integers(18, 75)),
            "OccupationID": int(rng.choice(occupation_ids)),
            "ReligionID": int(rng.choice(religion_ids)),
            "CasteID": int(rng.choice(caste_ids)),
            "GenderID": str(rng.choice(["M", "F"], p=[0.6, 0.4])),
        })
    complainant_df = pd.DataFrame(comp_rows)

    # ---- ArrestSurrender ----
    arr_rows = []
    arr_id = 1
    # Only for solved cases that have accused
    acc_by_case: dict[int, list[int]] = {}
    for row in acc_rows:
        acc_by_case.setdefault(int(row["CaseMasterID"]), []).append(int(row["AccusedMasterID"]))

    chargesheeted_statuses = {"Charge Sheeted", "Convicted", "Acquitted"}
    solved_rows = case_master_df[case_master_df["_status"].isin(chargesheeted_statuses)]
    for _, cr in solved_rows.iterrows():
        case_id = int(cr["CaseMasterID"])
        acc_list = acc_by_case.get(case_id, [])
        if not acc_list:
            continue
        for accused_mid in acc_list[:min(2, len(acc_list))]:
            arr_type = str(rng.choice(["Arrest", "Surrender"], p=[0.75, 0.25]))
            arr_date = cr["CrimeRegisteredDate"] + dt.timedelta(days=float(rng.integers(1, 90)))
            arr_rows.append({
                "ArrestSurrenderID": arr_id,
                "CaseMasterID": case_id,
                "ArrestSurrenderTypeID": arr_type,
                "ArrestSurrenderDate": arr_date,
                "ArrestSurrenderStateId": 1,
                "ArrestSurrenderDistrictId": dist_name_to_id.get(str(cr.get("_d_name", "Bengaluru City")), 1),
                "PoliceStationID": int(cr["PoliceStationID"]),
                "IOID": int(rng.choice(employee_ids)),
                "CourtID": cr["CourtID"],
                "AccusedMasterID": accused_mid,
                "IsAccused": True,
                "IsComplainantAccused": bool(rng.random() < 0.02),
            })
            arr_id += 1
    arrest_df = pd.DataFrame(arr_rows)

    # ---- ActSectionAssociation ----
    # Pre-build lookup dict O(14+n) instead of O(14n)
    from collections import defaultdict
    head_to_sections = defaultdict(list)
    for _, _r in crime_head_act_section_df.iterrows():
        head_to_sections[int(_r["CrimeHeadID"])].append((_r["ActCode"], _r["SectionCode"]))

    act_sec_rows = []
    asoc_id = 1
    for _, cr in case_master_df.iterrows():
        case_id = int(cr["CaseMasterID"])
        head_id = int(cr["CrimeMajorHeadID"])
        # look up sections for this crime head from pre-built dict
        relevant = head_to_sections.get(head_id, [("IPC", "379")])
        pair = random.choice(relevant)
        act_sec_rows.append({
            "CaseMasterID": case_id,
            "ActID": pair[0],
            "SectionID": pair[1],
            "ActOrderID": 1,
            "SectionOrderID": 1,
        })
    act_section_assoc_df = pd.DataFrame(act_sec_rows)

    # ---- ChargesheetDetails ----
    cs_rows = []
    cs_id = 1
    cs_eligible_statuses = {"Charge Sheeted", "Convicted", "Acquitted"}
    for _, cr in case_master_df.iterrows():
        if cr["_status"] not in cs_eligible_statuses:
            continue
        case_id = int(cr["CaseMasterID"])
        cs_date = cr["CrimeRegisteredDate"] + dt.timedelta(days=float(rng.integers(60, 180)))
        r = rng.random()
        cs_type = "A" if r < 0.80 else ("B" if r < 0.93 else "C")
        cs_rows.append({
            "CSID": cs_id,
            "CaseMasterID": case_id,
            "csdate": cs_date,
            "cstype": cs_type,
            "PolicePersonID": int(rng.choice(employee_ids)),
        })
        cs_id += 1
    chargesheet_df = pd.DataFrame(cs_rows)

    # ---- inv_arrestsurrenderaccused (junction) ----
    junc_rows = []
    if len(arrest_df) > 0:
        for _, row in arrest_df.iterrows():
            junc_rows.append({
                "ArrestSurrenderID": int(row["ArrestSurrenderID"]),
                "AccusedMasterID": int(row["AccusedMasterID"]),
            })
    junction_df = pd.DataFrame(junc_rows)

    # Drop temp columns from CaseMaster before returning
    case_master_clean = case_master_df.drop(columns=_temp_cols, errors="ignore")

    return {
        # Masters
        "State": state_df,
        "District": district_df,
        "UnitType": unit_type_df,
        "Unit": unit_df,
        "Rank": rank_df,
        "Designation": designation_df,
        "Employee": employee_df,
        "CaseCategory": case_category_df,
        "GravityOffence": gravity_df,
        "CrimeHead": crime_head_df,
        "CrimeSubHead": crime_sub_head_df,
        "CaseStatusMaster": case_status_df,
        "Court": court_df,
        "Act": act_df,
        "Section": section_df,
        "CrimeHeadActSection": crime_head_act_section_df,
        "CasteMaster": caste_df,
        "ReligionMaster": religion_df,
        "OccupationMaster": occupation_df,
        # Facts
        "CaseMaster": case_master_clean,
        "Inv_OccuranceTime": pd.DataFrame(occurrence_rows),
        "ComplainantDetails": complainant_df,
        "Victim": victim_df,
        "Accused": accused_df,
        "ArrestSurrender": arrest_df,
        "ActSectionAssociation": act_section_assoc_df,
        "ChargesheetDetails": chargesheet_df,
        "inv_arrestsurrenderaccused": junction_df,
    }


# -------------------------------------------------------- MAIN

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200000)
    args = ap.parse_args()

    from app.core import store
    from app.models.manifest import EntitySpec
    from app.services import crime_pack
    from app.services.profiler import build_manifest

    DATAFRAMES = build(args.rows)

    con = duckdb.connect()
    for name, df in DATAFRAMES.items():
        pq = store.table_path("ksp-fir", name)
        pq.parent.mkdir(parents=True, exist_ok=True)
        # Register as DuckDB view, copy to parquet
        con.register(f"_df_{name}", df)
        con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM "_df_{name}"')
        con.execute(f"COPY \"{name}\" TO '{pq}' (FORMAT PARQUET)")
        print(f"  wrote {name}: {len(df):,} rows -> {pq}")

    con.execute(f'CREATE VIEW case_master_analytics AS {ANALYTICS_VIEW_SQL}')

    tables = list(DATAFRAMES) + ["case_master_analytics"]
    manifest = build_manifest(con, tables, name="KSP FIR Records (Official Schema)",
                              dataset_id="ksp-fir")

    # MATERIALIZE the resolved analytics view to parquet. The primary table is
    # queried many times by build_insights (spikes, risk, anomalies, MO, etc.);
    # as a view it re-runs the ~10-table join every query (spike_alerts alone was
    # ~12s) and blew AppSail's ~30s budget. As a baked parquet, every query is a
    # flat single-table scan — the same shape that keeps ksp-crime fast.
    pq = store.table_path("ksp-fir", "case_master_analytics")
    con.execute(f"COPY case_master_analytics TO '{pq}' (FORMAT PARQUET)")

    for t in manifest.tables:
        t.is_primary = (t.name == "case_master_analytics")
        t.view_sql = None  # primary is now a real parquet; no per-query view join

    # Explicit entity for the network
    manifest.entities = [EntitySpec(
        name="accused", table="Accused", id_column="AccusedMasterID",
        label_column="AccusedName", link_columns=["Phone", "UpiId", "Address"])]

    crime_pack.apply_if_match(manifest)
    manifest.source = "seed"
    store.save_manifest(manifest)
    print(f"\nDataset 'ksp-fir' registered (domain_pack={manifest.domain_pack})")


if __name__ == "__main__":
    main()
