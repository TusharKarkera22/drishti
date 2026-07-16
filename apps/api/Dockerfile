# Catalyst AppSail requires OCI images built for linux/amd64.
# Build: docker build --platform linux/amd64 -t lens-api .
FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV DATA_DIR=/srv/data
# Bake the demo datasets (ksp-crime + the alien hospital set) into the image so the
# AppSail container renders immediately on boot — /srv/data is otherwise ephemeral.
# seed_data/ is staged from the repo's data/ dir (gitignored); see docs/deploy_catalyst.md.
COPY seed_data /srv/data

# AppSail injects the listen port via X_ZOHO_CATALYST_LISTEN_PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${X_ZOHO_CATALYST_LISTEN_PORT:-9000}"]
