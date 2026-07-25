# Dockerfile — Peregrine release build
# Self-contained single-repo context. Used for published images and community builds.
#
# cf-core: installed from public Forgejo via requirements.txt
# cf-orch: BSL-licensed cloud inference client; installed only when the
#          forgejo_token BuildKit secret is present (release CI).
#          Community builds skip it gracefully — local Ollama/vllm still work.
#
# Release CI (Forgejo):
#   docker buildx build --secret id=forgejo_token,env=FORGEJO_TOKEN -t peregrine:latest .
#
# Community / source build:
#   docker buildx build -t peregrine:latest .
#
# Previously this file ran Streamlit (app/app.py). Streamlit was removed in
# peregrine#104. The runtime is now uvicorn (FastAPI). Dockerfile.cfcore remains
# for the cloud deployment on Heimdall, where sibling repos are available.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev curl libsqlcipher-dev git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# cf-orch BSL client — cloud inference routing for paid/premium tier.
# The --mount=type=secret keeps the token out of all image layers.
# If no secret is provided the pip install is skipped; the app falls back to
# local backends (Ollama, vllm) and tier gating blocks cloud-orch features.
RUN --mount=type=secret,id=forgejo_token \
    TOKEN=$(cat /run/secrets/forgejo_token 2>/dev/null || true) && \
    if [ -n "$TOKEN" ]; then \
      pip install --no-cache-dir \
        "git+https://x-access-token:${TOKEN}@git.opensourcesolarpunk.com/Circuit-Forge/circuitforge-orch.git@main" \
        && echo "cf-orch installed"; \
    else \
      echo "cf-orch skipped (community build — local backends available)"; \
    fi

# Chromium for Playwright-based scrapers (companyScraper, job board scraping)
RUN playwright install chromium && playwright install-deps chromium

COPY scrapers/ /app/scrapers/
COPY . .

# Strip gitignored secrets that may exist in a local checkout.
# Defense-in-depth: .dockerignore already excludes these, but an explicit rm
# guarantees they never appear in the image even if .dockerignore is misconfigured.
RUN rm -f config/user.yaml config/plain_text_resume.yaml config/notion.yaml \
          config/email.yaml config/tokens.yaml config/craigslist.yaml \
          config/adzuna.yaml .env

EXPOSE 8601

CMD ["uvicorn", "dev_api:app", "--host", "0.0.0.0", "--port", "8601"]
