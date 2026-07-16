import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import store
from app.core.config import CORS_ORIGINS
from app.routers import agents, alerts, analytics, datasets, graph, ingest, insights, intake, predict, query, reports
from app.services import alerts as alerts_svc


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sentinel loop: scans all datasets for new spikes on boot and every
    # ALERT_SCAN_INTERVAL_S thereafter (on Catalyst, a Cron hitting
    # POST /api/alerts/{id}/scan can replace this).
    task = asyncio.create_task(alerts_svc.scan_loop())
    # Pre-build link graphs in the background so the first Network request hits the cache
    # (~0.1s) instead of a cold ~15-35s build, which would exceed AppSail's ~30s request
    # timeout (→ HTTP 408 "Execution Time Exceeded").
    warm = asyncio.create_task(_prewarm_graphs())
    yield
    task.cancel()
    warm.cancel()


async def _prewarm_graphs() -> None:
    await asyncio.sleep(2)  # let initial health checks pass before the CPU-heavy build
    try:
        manifests = store.list_datasets()
    except Exception:
        return
    for m in manifests:
        if not getattr(m, "entities", None):
            continue  # only entity-bearing datasets (e.g. the crime pack) have a link graph
        try:
            # loads the baked graph into the in-process cache (fast) so /ego and /search
            # are instant on cold-start; /summary reads its own baked JSON.
            await asyncio.to_thread(graph._graph, m.id)
        except Exception:
            pass  # never let pre-warming crash startup


app = FastAPI(title="Drishti — Schema-Agnostic Intelligence Platform",
              version="0.2.0", lifespan=lifespan)

# Catalyst's AppSail gateway injects its own CORS headers. Adding ours on top produces
# DUPLICATE Access-Control-Allow-Origin headers, which browsers reject ("Failed to fetch").
# So enable app-level CORS only OFF Catalyst (local dev), detected by the absence of the
# gateway-injected listen port. No cookies/credentials are used, so wildcard is safe.
if not os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(datasets.router, prefix="/api/datasets", tags=["datasets"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(query.router, prefix="/api/query", tags=["query"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(intake.router, prefix="/api/intake", tags=["intake"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(predict.router, prefix="/api/predict", tags=["predict"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
