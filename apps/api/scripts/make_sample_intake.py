"""Generate a realistic *messy* crime-records CSV for demoing the Data Intake pipeline.
Mixed date/phone/money formats, category + district CASING variants, a few duplicate
person-name variants, exact duplicate rows, and some blanks — so the cleaners visibly
fire and the agent has real work to plan.

Run from apps/api:  PYTHONPATH=. .venv/bin/python scripts/make_sample_intake.py
Writes <repo>/samples/messy_crime_records.csv
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

from faker import Faker

fake = Faker("en_IN")
Faker.seed(7)
rnd = random.Random(7)

DISTRICTS = ["Bengaluru City", "Mysuru", "Mangaluru City", "Hubballi-Dharwad", "Belagavi City"]
CRIMES = ["Theft", "Cybercrime", "Assault", "Robbery", "Burglary"]


def messy_case(proper: str) -> str:
    """60% keep the proper form (so it wins as canonical), 40% a casing/space variant."""
    if rnd.random() < 0.4:
        return rnd.choice([proper.lower(), proper.upper(), f" {proper} ", f"{proper}  "])
    return proper


def messy_date(d) -> str:
    return d.strftime(rnd.choice(["%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y", "%Y-%m-%d"]))


def messy_phone() -> str:
    n = "9" + "".join(rnd.choice("0123456789") for _ in range(9))
    return rnd.choice([f"+91 {n[:5]} {n[5:]}", f"0{n}", n, f"+91-{n}", f"{n[:5]}-{n[5:]}"])


def messy_money() -> str:
    amt = rnd.choice([8000, 12000, 50000, 120000, 250000, 350000])
    return rnd.choice([f"₹{amt:,}", str(amt), f"₹ {amt:,}.00", f"Rs.{amt}"])


names = [fake.name() for _ in range(16)]
rows: list[dict] = []
for i in range(34):
    name = rnd.choice(names)
    if rnd.random() < 0.3:  # name variants -> entity resolution
        name = rnd.choice([f"{name} B", name.upper(), name.replace(" ", "  ")])
    rows.append({
        "fir_no": f"FIR/2026/{1000 + i}",
        "occurrence_date": messy_date(fake.date_between(start_date="-1y", end_date="today")),
        "district": messy_case(rnd.choice(DISTRICTS)),
        "crime_group": messy_case(rnd.choice(CRIMES)),
        "accused_name": name,
        "accused_phone": messy_phone() if rnd.random() > 0.12 else "",  # ~12% blank
        "property_loss": messy_money() if rnd.random() > 0.15 else "",  # ~15% blank
    })

for _ in range(3):  # exact duplicate rows
    rows.append(dict(rnd.choice(rows)))
rnd.shuffle(rows)

out = Path(__file__).resolve().parents[3] / "samples" / "messy_crime_records.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"wrote {out} ({len(rows)} rows)")
