"""Synthetic KSP-style crime data generator (v0, best-guess schema).

Re-target to the official schema (once released on the Resources tab) by
editing the CONFIG section only. Output goes through the SAME generic
ingestion pipeline as any user upload — proving schema-agnosticism.

Planted patterns the demo should "discover":
  1. A serial burglary ring: 8 people, shared phones, ~60 night-time cases
     across Bengaluru City / Tumakuru / Mysuru with the same MO.
  2. A cybercrime spike in Bengaluru City over the final 5 weeks.
  3. A theft hotspot that migrates across Bengaluru localities by quarter.
  4. A cyber-fraud money-mule network: 5 "kingpin" UPI handles collecting
     payouts across ~40 fraud cases (FIRs CYB/...) filed in 5 districts —
     only the shared UPI id links the otherwise-unconnected local mules.
  5. Alias identities: the same offender booked under name variants
     ("Manjunath Gowda" / "Manjunath Gowda B"), for fuzzy entity resolution.

Usage:  python scripts/generate_data.py --rows 200000 [--csv-only]
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

# ---------------------------------------------------------------- CONFIG

END = dt.datetime(2026, 5, 31)
START = END - dt.timedelta(days=3 * 365)

DISTRICTS = {  # name: (lat, lng, weight)
    "Bengaluru City": (12.9716, 77.5946, 30),
    "Bengaluru Rural": (13.2846, 77.6190, 5),
    "Mysuru": (12.2958, 76.6394, 8),
    "Mangaluru City": (12.8703, 74.8420, 6),
    "Belagavi": (15.8497, 74.4977, 6),
    "Hubballi-Dharwad": (15.3647, 75.1240, 6),
    "Kalaburagi": (17.3297, 76.8343, 5),
    "Ballari": (15.1394, 76.9214, 4),
    "Shivamogga": (13.9299, 75.5681, 4),
    "Tumakuru": (13.3392, 77.1010, 5),
    "Davanagere": (14.4644, 75.9218, 4),
    "Vijayapura": (16.8302, 75.7100, 3),
    "Hassan": (13.0068, 76.0996, 3),
    "Udupi": (13.3409, 74.7421, 3),
    "Raichur": (16.2076, 77.3563, 3),
}

STATIONS_PER_DISTRICT = 6

# district: (population, area km², urbanization %, literacy %) — approximate
# census-derived figures for each police district's footprint. Emitted as a
# separate `districts` table so per-capita rates and socio-demographic risk
# factors come from data, not code.
DEMOGRAPHICS = {
    "Bengaluru City": (9_600_000, 786, 100.0, 88.7),
    "Bengaluru Rural": (990_000, 2298, 27.1, 77.9),
    "Mysuru": (3_001_000, 6307, 41.5, 72.8),
    "Mangaluru City": (620_000, 184, 100.0, 94.0),
    "Belagavi": (4_779_000, 13415, 25.3, 73.5),
    "Hubballi-Dharwad": (1_050_000, 213, 100.0, 87.0),
    "Kalaburagi": (2_566_000, 10951, 32.6, 64.9),
    "Ballari": (2_452_000, 8450, 37.5, 67.4),
    "Shivamogga": (1_752_000, 8477, 35.6, 80.4),
    "Tumakuru": (2_678_000, 10597, 22.4, 75.1),
    "Davanagere": (1_946_000, 5924, 32.3, 75.7),
    "Vijayapura": (2_177_000, 10494, 23.2, 67.2),
    "Hassan": (1_776_000, 6814, 21.2, 76.1),
    "Udupi": (1_177_000, 3880, 28.4, 86.2),
    "Raichur": (1_929_000, 8440, 25.4, 59.6),
}

# crime_group: (weight, [peak hours], avg property loss or 0)
CRIME_GROUPS = {
    "Theft": (22, [10, 14, 19], 25000),
    "Vehicle Theft": (10, [21, 23, 2], 80000),
    "Burglary": (9, [1, 2, 3], 120000),
    "Robbery": (5, [20, 22, 23], 60000),
    "Assault": (12, [18, 20, 22], 0),
    "Cybercrime": (10, [11, 15, 17], 150000),
    "Fraud & Cheating": (9, [11, 14, 16], 300000),
    "Murder": (1, [22, 0, 2], 0),
    "Missing Person": (6, [8, 12, 18], 0),
    "Narcotics": (4, [21, 23, 1], 0),
    "Sexual Offences": (4, [20, 22, 0], 0),
    "Rioting": (3, [16, 18, 20], 0),
    "Domestic Violence": (5, [20, 21, 22], 0),
}

CRIME_HEADS = {
    "Theft": ["Pickpocketing", "Chain Snatching", "Mobile Theft", "Shop Theft"],
    "Vehicle Theft": ["Two-Wheeler Theft", "Car Theft", "Auto Theft"],
    "Burglary": ["House Break-in (Night)", "House Break-in (Day)", "Shop Break-in"],
    "Robbery": ["Street Robbery", "Highway Robbery", "Dacoity"],
    "Assault": ["Simple Hurt", "Grievous Hurt", "Affray"],
    "Cybercrime": ["UPI Fraud", "OTP Scam", "Investment App Fraud", "Sextortion", "Job Fraud"],
    "Fraud & Cheating": ["Cheating", "Forgery", "Chit Fund Fraud", "Land Fraud"],
    "Murder": ["Murder", "Attempt to Murder"],
    "Missing Person": ["Missing Adult", "Missing Minor"],
    "Narcotics": ["NDPS Possession", "NDPS Peddling"],
    "Sexual Offences": ["Harassment", "POCSO", "Assault on Woman"],
    "Rioting": ["Unlawful Assembly", "Rioting"],
    "Domestic Violence": ["498A Cruelty", "Dowry Harassment"],
}

MONTH_FACTOR = [0.95, 0.92, 1.0, 1.05, 1.1, 1.0, 0.98, 1.0, 1.02, 1.08, 1.05, 1.12]

# ---- Detection-outcome model (case status is NOT random — it's a learnable,
# non-leaked function of case features). Mirrors scripts/generate_fir_data.py's
# model exactly (same rationale — see that file's comments) minus the gravity
# term, since this schema (v0 "incidents" table) carries no gravity column.
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
# Values tuned (x3 vs. a first-pass draft) via
# .superpowers/sdd/ml-realism-report.md's sweep — same constants as
# generate_fir_data.py (minus gravity) so both datasets land in the target
# [0.72, 0.90] AUC band without any single feature dominating.
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
DET_B0 = 0.35
DET_B_LEAD = 3.2
DET_B_DELAY = 1.0
DET_SIGMA = 0.4
REPORT_DELAY_MEAN_H = 18.0
REPORT_DELAY_STD_H = 18.0


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


# ------------------------------------------------------------- GENERATOR

rng = np.random.default_rng(42)
random.seed(42)
fake = Faker("en_IN")
Faker.seed(42)


def _stations() -> dict[str, list[tuple[str, float, float]]]:
    out = {}
    for d, (lat, lng, _) in DISTRICTS.items():
        sts = []
        for i in range(STATIONS_PER_DISTRICT):
            slat = lat + rng.normal(0, 0.06)
            slng = lng + rng.normal(0, 0.06)
            sts.append((f"{d} PS-{i + 1}", slat, slng))
        out[d] = sts
    return out


def _sample_time(n: int, peak_hours: list[int]) -> list[dt.datetime]:
    days = (END - START).days
    out = []
    weights = np.array([MONTH_FACTOR[(START + dt.timedelta(days=int(x))).month - 1]
                        for x in range(days)])
    weights /= weights.sum()
    day_idx = rng.choice(days, size=n, p=weights)
    for di in day_idx:
        base = START + dt.timedelta(days=int(di))
        hour = int(rng.choice(peak_hours)) if rng.random() < 0.55 else int(rng.integers(0, 24))
        out.append(base.replace(hour=hour, minute=int(rng.integers(0, 60))))
    return out


def generate(rows: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stations = _stations()
    d_names = list(DISTRICTS)
    d_weights = np.array([w for _, _, w in DISTRICTS.values()], dtype=float)
    d_weights /= d_weights.sum()
    g_names = list(CRIME_GROUPS)
    g_weights = np.array([w for w, _, _ in CRIME_GROUPS.values()], dtype=float)
    g_weights /= g_weights.sum()

    n_base = rows
    districts = rng.choice(d_names, size=n_base, p=d_weights)
    groups = rng.choice(g_names, size=n_base, p=g_weights)

    records = []
    for i in range(n_base):
        d, grp = districts[i], groups[i]
        st_name, st_lat, st_lng = random.choice(stations[d])
        ts = _sample_time(1, CRIME_GROUPS[grp][1])[0]

        # Planted pattern 3: migrating theft hotspot in Bengaluru by quarter
        if d == "Bengaluru City" and grp == "Theft" and rng.random() < 0.35:
            quarter = (ts.month - 1) // 3
            centers = [(12.935, 77.61), (12.98, 77.64), (13.01, 77.555), (12.91, 77.50)]
            st_lat, st_lng = centers[quarter]

        lat = st_lat + rng.normal(0, 0.015)
        lng = st_lng + rng.normal(0, 0.015)
        loss = CRIME_GROUPS[grp][2]
        records.append({
            "district": d, "police_station": st_name, "crime_group": grp,
            "crime_head": random.choice(CRIME_HEADS[grp]),
            "occurrence_ts": ts,
            "latitude": round(lat, 6), "longitude": round(lng, 6),
            "property_loss_value": int(max(rng.normal(loss, loss * 0.6), 0)) if loss else 0,
        })

    # Planted pattern 2: cybercrime spike in Bengaluru City, last 5 weeks
    spike_n = max(int(n_base * 0.006), 200)
    for _ in range(spike_n):
        ts = END - dt.timedelta(days=float(rng.integers(0, 35)),
                                hours=float(rng.integers(0, 24)))
        st_name, st_lat, st_lng = random.choice(stations["Bengaluru City"])
        records.append({
            "district": "Bengaluru City", "police_station": st_name,
            "crime_group": "Cybercrime",
            "crime_head": random.choice(["Investment App Fraud", "UPI Fraud"]),
            "occurrence_ts": ts,
            "latitude": round(st_lat + rng.normal(0, 0.02), 6),
            "longitude": round(st_lng + rng.normal(0, 0.02), 6),
            "property_loss_value": int(max(rng.normal(250000, 150000), 5000)),
        })

    inc = pd.DataFrame(records)
    inc = inc.sample(frac=1, random_state=42).reset_index(drop=True)
    inc.insert(0, "fir_no", [
        f"{r.district[:3].upper().replace(' ', '')}/{r.occurrence_ts.year}/{i + 1:06d}"
        for i, r in enumerate(inc.itertuples())
    ])
    report_delay_h = rng.exponential(18, len(inc))
    inc["reported_ts"] = inc["occurrence_ts"] + pd.to_timedelta(report_delay_h, unit="h")
    inc["description"] = inc["crime_head"] + " reported at " + inc["police_station"]

    # ---- realistic, learnable, non-leaked detection outcome ----
    # `has_lead`: latent per-row Bernoulli flag by crime type (see HAS_LEAD_P
    # module docstring) — NOT written to the `incidents` table, used only to
    # derive case_status here and to gate accused generation below, so it can
    # never leak into ml.py (which reads real manifest columns by semantic
    # role, and this never becomes one).
    lead_p_vec = inc["crime_group"].map(HAS_LEAD_P).to_numpy(dtype=float)
    has_lead = rng.random(len(inc)) < lead_p_vec
    type_logit_vec = inc["crime_group"].map(DETECTION_TYPE_LOGIT).to_numpy(dtype=float)
    delay_z = (report_delay_h - REPORT_DELAY_MEAN_H) / REPORT_DELAY_STD_H
    noise_vec = rng.normal(0, DET_SIGMA, len(inc))
    logit = (DET_B0 + type_logit_vec + DET_B_LEAD * has_lead.astype(float)
             - DET_B_DELAY * delay_z + noise_vec)
    p_detect = _sigmoid(logit)
    detected = rng.random(len(inc)) < p_detect

    detected_statuses = np.array(["Chargesheeted", "Convicted", "Acquitted"])
    detected_probs = [0.55, 0.28, 0.17]
    days_since_occ = (END - inc["occurrence_ts"]).dt.days.to_numpy(dtype=float)
    p_still_open = np.clip(1.0 - days_since_occ / 240.0, 0.05, 0.92)
    still_open = rng.random(len(inc)) < p_still_open

    case_status = np.where(
        detected,
        rng.choice(detected_statuses, size=len(inc), p=detected_probs),
        np.where(still_open, "Under Investigation", "Closed - Undetected"),
    )
    inc["case_status"] = case_status
    inc["_has_lead"] = has_lead  # dropped before return; used for Accused gen below

    # ----- accused persons (power-law: few prolific repeat offenders)
    n_persons = max(len(inc) // 6, 50)
    p_names = [fake.name() for _ in range(n_persons)]
    upi_banks = ["okhdfc", "okaxis", "ybl", "paytm", "okicici"]
    persons = pd.DataFrame({
        "person_id": [f"P{i + 1:06d}" for i in range(n_persons)],
        "name": p_names,
        "age": rng.integers(16, 65, n_persons),
        "gender": rng.choice(["Male", "Female"], n_persons, p=[0.85, 0.15]),
        "phone": [f"9{rng.integers(100000000, 999999999)}" for _ in range(n_persons)],
        "address": [f"{fake.street_address()}, {d}" for d in
                    rng.choice(d_names, n_persons, p=d_weights)],
        "upi_id": [
            f"{p_names[i].split()[0].lower()}.{i}@{random.choice(upi_banks)}"
            if random.random() < 0.65 else None
            for i in range(n_persons)
        ],
    })

    weights = rng.pareto(2.5, n_persons) + 1
    weights = np.minimum(weights, np.percentile(weights, 99.5))  # cap hyper-prolific outliers
    weights /= weights.sum()
    # Accused rows are generated for cases with a LEAD (_has_lead), not purely
    # by outcome status — this is what breaks the n_accused/status leak: most
    # has_lead cases got DETECTED (b_lead=+1.35 in the logit above), but some
    # has_lead cases are still open (Under Investigation) or even ended
    # undetected (the lead didn't pan out), so n_accused>0 is a strong but
    # IMPERFECT predictor of detection, exactly like real investigations.
    lead_idx = inc.index[inc["_has_lead"]]
    # kept for the alias-pattern pool below, which wants "solved" cases
    # specifically (a convicted/acquitted/chargesheeted alias makes narrative
    # sense); independent of the has_lead-driven Accused generation above.
    solved_mask = inc["case_status"].isin(["Chargesheeted", "Convicted", "Acquitted"])
    solved_idx = inc.index[solved_mask]
    acc_rows = []
    for fir_idx in lead_idx:
        for _ in range(int(rng.choice([1, 1, 1, 2, 2, 3]))):
            p = persons.iloc[int(rng.choice(n_persons, p=weights))]
            acc_rows.append({"accused_id": f"A{len(acc_rows) + 1:07d}",
                             "person_id": p.person_id, "name": p["name"],
                             "age": p.age, "gender": p.gender, "phone": p.phone,
                             "address": p.address, "upi_id": p.upi_id,
                             "fir_no": inc.at[fir_idx, "fir_no"]})

    # ----- Planted pattern 5: alias identities — same offender booked under
    # name variants; only fuzzy entity resolution connects them.
    alias_pairs = [
        ("Manjunath Gowda", "Manjunath Gowda B", "Bengaluru City"),
        ("Syed Imran Pasha", "Imran Pasha Syed", "Mysuru"),
        ("Ravi Kumar H", "Ravi Kumar", "Davanagere"),
    ]
    for k, (n1, n2, d) in enumerate(alias_pairs):
        age = int(rng.integers(25, 50))
        for v, nm in enumerate((n1, n2)):
            alias = {
                "person_id": f"P7{k}{v:04d}", "name": nm, "age": age,
                "gender": "Male",
                "phone": f"9{rng.integers(100000000, 999999999)}",
                "address": f"{fake.street_address()}, {d}",
                "upi_id": None,
            }
            pool = [i for i in solved_idx if inc.at[i, "district"] == d]
            for fir_idx in random.sample(pool, k=5):
                acc_rows.append({"accused_id": f"A7{len(acc_rows):06d}", **alias,
                                 "fir_no": inc.at[fir_idx, "fir_no"]})

    # ----- Planted pattern 1: serial burglary ring across 3 districts
    ring_districts = ["Bengaluru City", "Tumakuru", "Mysuru"]
    ring = []
    shared_phones = [f"98860{rng.integers(10000, 99999)}" for _ in range(4)]
    for i in range(8):
        ring.append({
            "person_id": f"P9{i:05d}", "name": fake.name(),
            "age": int(rng.integers(22, 40)), "gender": "Male",
            "phone": shared_phones[i // 2],  # pairs share a phone — the hidden link
            "address": f"{fake.street_address()}, {ring_districts[i % 3]}",
            "upi_id": None,
        })
    ring_cases = []
    for j in range(60):
        d = ring_districts[j % 3]
        st_name, st_lat, st_lng = random.choice(stations[d])
        ts = START + dt.timedelta(days=float(rng.integers(60, (END - START).days)),
                                  hours=float(rng.choice([1, 2, 3])))
        fir = f"RING/{ts.year}/{j + 1:04d}"
        ring_cases.append({
            "fir_no": fir, "district": d, "police_station": st_name,
            "crime_group": "Burglary", "crime_head": "House Break-in (Night)",
            "occurrence_ts": ts, "reported_ts": ts + dt.timedelta(hours=8),
            "latitude": round(st_lat + rng.normal(0, 0.01), 6),
            "longitude": round(st_lng + rng.normal(0, 0.01), 6),
            "property_loss_value": int(rng.normal(200000, 50000)),
            "case_status": "Under Investigation",
            "description": "House Break-in (Night) — gas cutter used on locks, CCTV avoided",
        })
        for member in random.sample(ring, k=2):
            acc_rows.append({"accused_id": f"A9{len(acc_rows):06d}", **member, "fir_no": fir})
    inc = pd.concat([inc, pd.DataFrame(ring_cases)], ignore_index=True)

    # ----- Planted pattern 4: cyber-fraud money-mule network across 5 districts
    mule_districts = ["Bengaluru City", "Mangaluru City", "Hubballi-Dharwad",
                      "Kalaburagi", "Mysuru"]
    kingpin_upis = [f"quickreturns{k}@ybl" for k in range(1, 6)]
    mules = []
    for i in range(25):
        mules.append({
            "person_id": f"P8{i:05d}", "name": fake.name(),
            "age": int(rng.integers(19, 45)),
            "gender": str(rng.choice(["Male", "Female"], p=[0.7, 0.3])),
            "phone": f"9{rng.integers(100000000, 999999999)}",
            "address": f"{fake.street_address()}, {mule_districts[i % 5]}",
            "upi_id": kingpin_upis[i % 5],  # payouts funnel to the kingpin handle
        })
    mule_cases = []
    for j in range(40):
        d = mule_districts[j % 5]
        st_name, st_lat, st_lng = random.choice(stations[d])
        ts = END - dt.timedelta(days=float(rng.integers(0, 400)),
                                hours=float(rng.integers(0, 24)))
        fir = f"CYB/{ts.year}/{j + 1:04d}"
        mule = random.choice([m for i, m in enumerate(mules) if i % 5 == j % 5])
        mule_cases.append({
            "fir_no": fir, "district": d, "police_station": st_name,
            "crime_group": "Cybercrime",
            "crime_head": random.choice(["Investment App Fraud", "UPI Fraud"]),
            "occurrence_ts": ts, "reported_ts": ts + dt.timedelta(hours=30),
            "latitude": round(st_lat + rng.normal(0, 0.02), 6),
            "longitude": round(st_lng + rng.normal(0, 0.02), 6),
            "property_loss_value": int(max(rng.normal(450000, 200000), 20000)),
            "case_status": "Under Investigation",
            "description": f"Investment app fraud — victim payout routed via UPI handle {mule['upi_id']}",
        })
        acc_rows.append({"accused_id": f"A8{len(acc_rows):06d}", **mule, "fir_no": fir})
    inc = pd.concat([inc, pd.DataFrame(mule_cases)], ignore_index=True)

    accused = pd.DataFrame(acc_rows)
    inc = inc.drop(columns=["_has_lead"])  # internal-only; never part of the schema

    # ----- victims
    vic_rows = []
    vic_sample = inc.sample(frac=0.7, random_state=7)
    for r in vic_sample.itertuples():
        vic_rows.append({
            "victim_id": f"V{len(vic_rows) + 1:07d}", "name": fake.name(),
            "age": int(rng.integers(12, 80)),
            "gender": str(rng.choice(["Male", "Female"], p=[0.55, 0.45])),
            "fir_no": r.fir_no,
        })
    victims = pd.DataFrame(vic_rows)

    districts = pd.DataFrame([
        {"district": d, "population": pop, "area_km2": area,
         "density_per_km2": round(pop / area, 1),
         "urbanization_pct": urban, "literacy_pct": lit}
        for d, (pop, area, urban, lit) in DEMOGRAPHICS.items()
    ])
    return inc, accused, victims, districts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200000)
    ap.add_argument("--csv-only", action="store_true",
                    help="only write CSVs, skip registering the dataset")
    ap.add_argument("--dataset-id", default="ksp-crime")
    args = ap.parse_args()

    inc, accused, victims, districts = generate(args.rows)
    out = (Path(__file__).resolve().parents[1] / ".." / ".." / "data" / "raw").resolve()
    out.mkdir(parents=True, exist_ok=True)
    inc.to_csv(out / "incidents.csv", index=False)
    accused.to_csv(out / "accused.csv", index=False)
    victims.to_csv(out / "victims.csv", index=False)
    districts.to_csv(out / "districts.csv", index=False)
    print(f"CSVs written to {out}: incidents={len(inc)}, accused={len(accused)}, "
          f"victims={len(victims)}, districts={len(districts)}")

    if args.csv_only:
        return

    # Register through the SAME generic pipeline as a user upload.
    from app.core import store
    from app.services import crime_pack
    from app.services.profiler import build_manifest

    con = duckdb.connect()
    con.register("incidents_df", inc)
    con.register("accused_df", accused)
    con.register("victims_df", victims)
    con.register("districts_df", districts)
    for t in ("incidents", "accused", "victims", "districts"):
        con.execute(f'CREATE TABLE "{t}" AS SELECT * FROM {t}_df')
        pq = store.table_path(args.dataset_id, t)
        pq.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY \"{t}\" TO '{pq}' (FORMAT PARQUET)")

    manifest = build_manifest(con, ["incidents", "accused", "victims", "districts"],
                              name="KSP Crime Records (Synthetic)",
                              dataset_id=args.dataset_id)
    crime_pack.apply_if_match(manifest)
    manifest.source = "seed"
    store.save_manifest(manifest)
    print(f"Dataset '{args.dataset_id}' registered (domain pack: {manifest.domain_pack})")


if __name__ == "__main__":
    main()
