"""Smoke-test build_insights against a seed/registered dataset.
Run from apps/api:  PYTHONPATH=. .venv/bin/python scripts/smoke_insights.py"""
from app.core import store
from app.services import insights

mans = store.list_datasets()
if not mans:
    print("no datasets in store — ingest one first"); raise SystemExit(1)
target = next((m for m in mans if getattr(m, "domain_pack", "") == "crime"), mans[0])
out = insights.build_insights(target.id)
print(f"dataset: {target.id}  ({target.name})")
print(f"signals_used: {out['signals_used']}")
for f in out["findings"]:
    print(f"  [{f['severity']:3d}] {f['type']:12s} {f['title']}")
print(f"forecast.confidence: {out['forecast'].get('confidence')}  "
      f"areas: {[a['area'] for a in out['forecast'].get('areas', [])]}")
print(f"backtest: {out['backtest']}")
