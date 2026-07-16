<div align="center">

<img src="screenshots/emblem.png" width="88" alt="DRISHTI"/>

# DRISHTI

**दृष्टि · ದೃಷ್ಟಿ — "vision"**

### A schema-agnostic, predictive crime-intelligence platform

*KSP Datathon 2026 · Problem Statement 2 (AI-driven crime analytics & visualization)*
Karnataka State Police × Zoho Catalyst × Hack2skill

**[▶ Live demo](https://project-rainfall-60073652192.development.catalystserverless.in/app/)**  ·  **[🎥 Demo video](https://drive.google.com/file/d/1s9tGzW0aRIylbctSTfnpKuuN7JK2ilQu/view?usp=sharing)**  ·  Built by **Team HawkEye**

</div>

---

## The problem

Karnataka's police register **lakhs of FIRs a year**, but the intelligence in that data is trapped — scattered across a thousand stations, in Excel sheets, in formats no two officers write the same way. The data is there; it's just *stuck in silos*.

**DRISHTI turns those silos into foresight.** Drop any dataset — a district's messy Excel files or the official 28-table FIR schema — and it profiles it, links it, ranks today's problems, **predicts which open cases will go undetected**, and explains every number. No per-dataset code. Bilingual (English / ಕನ್ನಡ). Governed by design.

---

## What it looks like

**Answer-first Insights — the top problems, ranked, with a live forecast that backtests itself**
![Insights](screenshots/insights.png)

**Criminal network — repeat offenders across jurisdictions, one click to their full MO profile**
![Network](screenshots/network.png)

**Geospatial hotspots + AI agents**

<img src="screenshots/map.png" width="49%"/> <img src="screenshots/agents.png" width="49%"/>

---

## How it answers Problem Statement 2

| PS-2 asks for… | DRISHTI delivers |
|---|---|
| Ingest their data (Excel silos / FIR schema) | Schema-agnostic profiler — drop 4 Excel files or the official 28-table FIR schema; foreign keys resolve to names, zero config |
| Spatiotemporal hotspots | Grid hotspot map with hour-band + category filters; per-district 7-day risk (composite ↔ per-lakh) |
| Repeat-offender tracking + MO | Link graph over shared phones / addresses / UPI; one-click offender profile — cases across N districts + MO signature |
| Sociological insights ("the why") | Crime-rate vs urbanization / literacy / density correlation (r-values), socio-demographic exposure in risk scoring |
| Emerging crime types | Per-typology trend ranking — the fastest-rising category, weeks early |
| **Predictive intelligence** | **Case-detection model** — flags open cases likely to go undetected (honest, backtested AUC), + expected resolution time / stall risk |
| Replace the annual handbook | Live **Digital Crime Handbook** — KPIs, trends, risk, network highlights, AI executive summary → print to PDF |
| Natural-language access | **Four AI agents** (Vishleshak / Rakshak / Sutradhar / Prahari) that plan, run live tool-calls, and show every step |

---

## Four pillars

- **🧩 Schema-agnostic** — every UI surface renders off *semantic roles* (timestamp, area, category, person, money, FK…) inferred by a profiler, never hardcoded column names. The same engine runs on crime, accidents, or a hospital CSV.
- **🔮 Predictive** — supervised models (scikit-learn, trained offline, baked & served in ms) score every open case: detection likelihood + resolution time. Honest, backtested — no inflated numbers.
- **🗣 Bilingual** — the entire UI *and* the AI's narration speak English or ಕನ್ನಡ, one toggle. For the officers who actually use it.
- **⚖️ Governed** — a **classical engine computes every number** (DuckDB / numpy / scikit-learn / NetworkX); the LLM only *plans and narrates*. Models use case facts only — **never caste or religion**. Human-in-the-loop, court-defensible audit trail.

---

## Architecture

```
Browser (Next.js static export) ──HTTPS──▶ FastAPI (Docker, Catalyst AppSail)
  Insights · Map · Network · Agents            Routers → Services:
  Handbook · ECharts · Cytoscape · MapLibre     Profiler · Query · Analytics · Graph
        │                                        Insights · Predict · Append · Agents · Intake
        ▼                                                     │
  Catalyst Web Hosting                          ┌─────────────┴──────────────┐
                                     CLASSICAL ENGINE              AI (NARRATOR ONLY)
                                DuckDB/Parquet · manifest.json     QuickML — Qwen 2.5 14B
                                graph.pkl · baked ML models        plans tool-calls, writes
                                numpy · scikit-learn · NetworkX     grounded EN / ಕನ್ನಡ prose
```

**Golden rule:** classical code computes every statistic; the LLM never touches the numbers — model quality bounds the *prose*, never the *analytics*. Results are cached per data-version (instant on revisit); heavy compute is baked offline so requests stay within the platform's ~30s budget.

**Catalyst services:** AppSail (backend Docker), Web Client Hosting (frontend), QuickML LLM Serving (Qwen 2.5 14B).

---

## Repo layout

```
apps/api    FastAPI backend — ingest/profile, query, analytics, graph, agents, insights,
            predict, append, intake, reports  (Python 3.13)
apps/web    Next.js frontend, static export (guided pipeline UI, bilingual, ECharts/Cytoscape/MapLibre)
apps/api/scripts   synthetic data generators (KSP crime 200k · official 28-table FIR · Excel silos)
samples/    Excel-silo demo files (drop them into the live app)
screenshots/  images used in this README
```

Storage is Parquet-per-table + a `manifest.json` per dataset, queried through in-memory DuckDB — no database server. The manifest is the single contract between backend and frontend.

---

## Run locally

**Backend** (Python ≥ 3.13):
```bash
cd apps/api
python -m venv .venv && .venv/bin/pip install -r requirements.txt
# generate demo data (200k crime incidents + linked accused/victims, with planted patterns)
DATA_DIR=$(pwd)/seed_data PYTHONPATH=. .venv/bin/python scripts/generate_data.py --rows 200000
# official 28-table FIR-schema dataset + baked graph + ML models:
DATA_DIR=$(pwd)/seed_data PYTHONPATH=. .venv/bin/python scripts/generate_fir_data.py --rows 50000
DATA_DIR=$(pwd)/seed_data PYTHONPATH=. .venv/bin/python scripts/build_graph_artifacts.py
DATA_DIR=$(pwd)/seed_data PYTHONPATH=. .venv/bin/python scripts/train_models.py
DATA_DIR=$(pwd)/seed_data PYTHONPATH=. .venv/bin/uvicorn app.main:app --port 8400
```

**Frontend:**
```bash
cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8400 npm run dev   # http://localhost:3000
```

Agents need an OpenAI-compatible LLM endpoint. Locally, [Ollama](https://ollama.com) works out of the box (`LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=qwen2.5:7b`); on Catalyst it's the QuickML LLM Serving endpoint.

**Key environment variables** (all optional for local; see `apps/api/app/core/config.py`):

| Variable | Purpose | Default |
|---|---|---|
| `DATA_DIR` | dataset storage root | `<repo>/apps/api/seed_data` |
| `LLM_BASE_URL` | OpenAI-compatible chat endpoint | `http://localhost:11434/v1` |
| `LLM_MODEL` | model name | `qwen2.5:7b` |
| `NEXT_PUBLIC_API_URL` | API base baked into the static frontend | `http://localhost:8400` |

*(No secrets are committed — QuickML/Catalyst credentials are supplied at deploy time via environment variables only.)*

**Tests:** `cd apps/api && .venv/bin/python -m pytest tests/ -q` — 135 passing.

---

## Deployment

Deployed **exclusively on Zoho Catalyst** (mandated): the API runs as a `linux/amd64` Docker service on **AppSail**, the Next.js static export is served from **Web Client Hosting**, and agents call a **QuickML LLM Serving** endpoint. Live: **[project-rainfall-…/app](https://project-rainfall-60073652192.development.catalystserverless.in/app)**.

---

## Team

**HawkEye** — Kiran Sala (lead) · Tushar Karkera — KSP Datathon 2026, Problem Statement 2.

<div align="center"><sub>from <em>where crime was</em> → to <em>which cases will stall, where it'll spike, and who's connected</em></sub></div>
