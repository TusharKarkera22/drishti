import os
from pathlib import Path

# Data lives in DATA_DIR as parquet + manifest JSON per dataset:
#   {DATA_DIR}/{dataset_id}/{table}.parquet
#   {DATA_DIR}/{dataset_id}/manifest.json
# DATA_DIR comes from the env in the container/AppSail; fall back to the repo's data/
# for local dev. The fallback is computed safely: at container depth
# (/srv/app/core/config.py) there is no parents[4], so guard the index — and use `or`
# so the fallback is only consulted when DATA_DIR is unset/empty.
_parents = Path(__file__).resolve().parents
_repo_data = (_parents[4] / "data") if len(_parents) > 4 else (Path.cwd() / "data")
DATA_DIR = Path(os.environ.get("DATA_DIR") or _repo_data).resolve()

# Swappable LLM endpoint.
#   LLM_PROVIDER=openai  -> OpenAI-compatible /chat/completions (Ollama, scripted mock, vLLM/TGI)
#   LLM_PROVIDER=quickml -> Zoho Catalyst QuickML LLM Serving (mandated on Catalyst).
# In quickml mode LLM_BASE_URL is the FULL chat URL (…/llm/chat) and CATALYST_ORG is required.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:7b")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
# CATALYST-ORG header value. On Catalyst AppSail the `CATALYST_`/`ZOHO_` env-var prefixes
# are RESERVED and rejected, so the deployable name is LENS_ORG_ID (CATALYST_ORG kept as a
# local-dev fallback).
CATALYST_ORG = os.environ.get("LENS_ORG_ID") or os.environ.get("CATALYST_ORG", "")

# QuickML auth: the backend self-mints short-lived access tokens from client credentials
# (client_credentials grant) so a long-running deploy never breaks at the ~1h token TTL.
# A static LLM_API_KEY (above), if set, takes precedence — handy for local testing.
# Deployable names are LENS_CLIENT_ID/LENS_CLIENT_SECRET (ZOHO_* is reserved on Catalyst);
# ZOHO_*/lowercase kept as fallbacks for the local .env.
ZOHO_CLIENT_ID = (os.environ.get("LENS_CLIENT_ID") or os.environ.get("ZOHO_CLIENT_ID")
                  or os.environ.get("client_id", ""))
ZOHO_CLIENT_SECRET = (os.environ.get("LENS_CLIENT_SECRET") or os.environ.get("ZOHO_CLIENT_SECRET")
                      or os.environ.get("client_secret", ""))
ZOHO_ACCOUNTS_URL = os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in").rstrip("/")
QUICKML_OAUTH_SCOPE = os.environ.get("QUICKML_OAUTH_SCOPE", "QuickML.deployment.READ")
QUICKML_OAUTH_SOID = os.environ.get("QUICKML_OAUTH_SOID") or (
    f"ZohoCatalyst.{CATALYST_ORG}" if CATALYST_ORG else "")
# QuickML's max_tokens is the TOTAL (input+output) context budget; the served Qwen 14B
# accepts at least 32k — 16k is ample for agent transcripts with tool results.
QUICKML_MAX_TOKENS = int(os.environ.get("QUICKML_MAX_TOKENS", "16384"))

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

# Public demo upload guardrails. Values are deliberately conservative enough
# for the seeded judge workflows while bounding memory, disk, and parse work.
MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "8"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UPLOAD_TOTAL_BYTES = int(
    os.environ.get("MAX_UPLOAD_TOTAL_BYTES", str(50 * 1024 * 1024))
)
MAX_UPLOAD_ROWS = int(os.environ.get("MAX_UPLOAD_ROWS", "250000"))
MAX_UPLOAD_REQUEST_BYTES = int(
    os.environ.get("MAX_UPLOAD_REQUEST_BYTES", str(MAX_UPLOAD_TOTAL_BYTES + 1024 * 1024))
)
MAX_XLSX_UNCOMPRESSED_BYTES = int(
    os.environ.get("MAX_XLSX_UNCOMPRESSED_BYTES", str(100 * 1024 * 1024))
)
MAX_XLSX_MEMBER_BYTES = int(
    os.environ.get("MAX_XLSX_MEMBER_BYTES", str(50 * 1024 * 1024))
)
MAX_XLSX_MEMBERS = int(os.environ.get("MAX_XLSX_MEMBERS", "2048"))
MAX_XLSX_COMPRESSION_RATIO = int(os.environ.get("MAX_XLSX_COMPRESSION_RATIO", "200"))
