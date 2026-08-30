import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.core import store
from app.core.config import CORS_ORIGINS, MAX_UPLOAD_REQUEST_BYTES
from app.routers import agents, alerts, analytics, datasets, graph, ingest, insights, intake, investigations, predict, query, reports, temporal
from app.services import alerts as alerts_svc

UPLOAD_BODY_LIMIT_BYTES = MAX_UPLOAD_REQUEST_BYTES
_UPLOAD_PATHS = ("/api/ingest", "/api/intake/clean")


class _UploadBodyTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    """Bound upload bodies before Starlette's multipart parser can spool them."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(_UPLOAD_PATHS):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > UPLOAD_BODY_LIMIT_BYTES:
                    await JSONResponse({"detail": "upload request body is too large"}, status_code=413)(
                        scope, receive, send
                    )
                    return
            except ValueError:
                await JSONResponse({"detail": "invalid Content-Length header"}, status_code=400)(
                    scope, receive, send
                )
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > UPLOAD_BODY_LIMIT_BYTES:
                    raise _UploadBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _UploadBodyTooLarge:
            await JSONResponse({"detail": "upload request body is too large"}, status_code=413)(
                scope, receive, send
            )


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
app.add_middleware(UploadBodyLimitMiddleware)

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
app.include_router(temporal.router, prefix="/api/temporal", tags=["temporal"])
app.include_router(investigations.router, prefix="/api/investigations", tags=["investigations"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
