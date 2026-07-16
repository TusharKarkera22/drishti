"""Pre-build the link graph + summary and write them beside each dataset, so the
deployed container LOADS them (~0.2s) instead of rebuilding (~15-35s, which exceeds
Catalyst AppSail's ~30s request timeout and 408s on a cold start).

Run after (re)generating data and before `docker build`, pointing DATA_DIR at the
image's seed staging:

    cd apps/api
    DATA_DIR=$(pwd)/seed_data PYTHONPATH=. .venv/bin/python scripts/build_graph_artifacts.py

Writes {DATA_DIR}/{dataset_id}/graph.pkl + summary.json for every dataset that has
linkable entities (e.g. the crime pack). Datasets without entities are skipped.
"""
from __future__ import annotations

import json
import pickle
import time

from fastapi.encoders import jsonable_encoder

from app.core import store
from app.services import graph as svc


def main() -> None:
    for m in store.list_datasets():
        if not m.entities:
            print(f"skip {m.id}: no linkable entities")
            continue
        t = time.time()
        g = svc.build_graph(m.id, m)
        summary = svc.graph_summary(g, m)
        d = store.dataset_dir(m.id)
        with (d / "graph.pkl").open("wb") as f:
            pickle.dump(g, f, protocol=pickle.HIGHEST_PROTOCOL)
        (d / "summary.json").write_text(json.dumps(jsonable_encoder(summary)))
        print(f"{m.id}: baked graph.pkl + summary.json "
              f"({g.number_of_nodes()} nodes, {g.number_of_edges()} edges) in {time.time()-t:.1f}s")


if __name__ == "__main__":
    main()
