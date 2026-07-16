"""Pre-train the Predictive-Intelligence models (detection + duration) and
write them beside each dataset, so the deployed container LOADS them
(routers/predict.py) instead of training on the request path — training is
CPU-heavy (permutation_importance, cross-validated fit) and Catalyst AppSail
has a ~30s request timeout.

Run after (re)generating data and before `docker build`, pointing DATA_DIR at
the image's seed staging (same convention as scripts/build_graph_artifacts.py):

    cd apps/api
    DATA_DIR=$(pwd)/seed_data PYTHONPATH=. .venv/bin/python scripts/train_models.py

Writes {DATA_DIR}/{dataset_id}/models/detection.joblib (+ duration.joblib when
available) + models/meta.json for every dataset with a STATUS column on its
primary table. Datasets without one (no closed/undetected label to train on)
are skipped and logged — e.g. a dataset with no crime-style lifecycle at all.
"""
from __future__ import annotations

import json
import time

from app.core import store
from app.services import ml as svc


def _bundle_meta(bundle: dict) -> dict:
    """Strip the non-JSON-serialisable `model` estimator out of a bundle for
    meta.json, keeping only the reportable numbers."""
    return {k: v for k, v in bundle.items() if k not in ("model",)}


def main() -> None:
    for m in store.list_datasets():
        t = m.primary_table()
        if not t:
            print(f"skip {m.id}: no tables")
            continue

        t0 = time.time()
        det = svc.train_detection(m.id)
        if not det.get("available"):
            print(f"skip {m.id}: detection unavailable ({det.get('reason')})")
            continue

        dur = svc.train_duration(m.id)

        models_dir = store.dataset_dir(m.id) / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        import joblib
        joblib.dump(det, models_dir / "detection.joblib")
        meta = {"detection": _bundle_meta(det)}
        if dur.get("available"):
            joblib.dump(dur, models_dir / "duration.joblib")
            meta["duration"] = _bundle_meta(dur)
        else:
            meta["duration"] = {"available": False, "reason": dur.get("reason")}
        (models_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))

        dur_txt = (f"duration MAE={dur['mae']}d (n={dur['n_train']})"
                   if dur.get("available") else f"duration unavailable ({dur.get('reason')})")
        print(f"{m.id}: baked detection AUC={det['auc']} base_rate={det['base_rate']} "
              f"(n={det['n_train']}); {dur_txt} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
