#!/usr/bin/env bash
# podman-standalone.sh — Peregrine rootful Podman setup (no Compose)
#
# For beta testers running system Podman (non-rootless) with systemd.
# Mirrors the manage.sh "remote" profile: app + SearXNG only.
# Ollama/vLLM/vision are expected as host services if needed.
#
# ── Prerequisites ────────────────────────────────────────────────────────────
#   1. Clone the repo:
#        sudo git clone <repo-url> /opt/peregrine
#
#   2. Build the app image:
#        cd /opt/peregrine && sudo podman build -t localhost/peregrine:latest .
#
#   3. Create a config directory and copy the example configs:
#        sudo mkdir -p /opt/peregrine/{config,data}
#        sudo cp /opt/peregrine/config/*.example /opt/peregrine/config/
#        # Edit /opt/peregrine/config/llm.yaml, notion.yaml, etc. as needed
#
#   4. Run this script:
#        sudo bash /opt/peregrine/podman-standalone.sh
#
# ── After setup — generate systemd unit files ────────────────────────────────
#   sudo podman generate systemd --new --name peregrine-searxng \
#     | sudo tee /etc/systemd/system/peregrine-searxng.service
#   sudo podman generate systemd --new --name peregrine \
#     | sudo tee /etc/systemd/system/peregrine.service
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now peregrine-searxng peregrine
#
# ── SearXNG ──────────────────────────────────────────────────────────────────
#   Peregrine expects a SearXNG instance with JSON format enabled.
#   If you already run one, skip the SearXNG container and set the URL in
#   config/llm.yaml (searxng_url key). The default is http://localhost:8888.
#
# ── Ports ────────────────────────────────────────────────────────────────────
#   Peregrine UI  → http://localhost:8501
#
# ── To use a different Streamlit port ────────────────────────────────────────
#   Uncomment the CMD override at the bottom of the peregrine run block and
#   set PORT= to your desired port. The Dockerfile default is 8501.
#
set -euo pipefail

REPO_DIR=/opt/peregrine
DATA_DIR=/opt/peregrine/data
DOCS_DIR=/Library/Documents/JobSearch   # ← adjust to your docs path
TZ=America/Los_Angeles

# ── Peregrine App ─────────────────────────────────────────────────────────────
# Image is built locally — no registry auto-update label.
# To update: sudo podman build -t localhost/peregrine:latest /opt/peregrine
#            sudo podman restart peregrine
#
# Env vars: ANTHROPIC_API_KEY, OPENAI_COMPAT_URL, OPENAI_COMPAT_KEY are
# optional — only needed if you're using those backends in config/llm.yaml.
#
sudo podman run -d \
  --name=peregrine \
  --restart=unless-stopped \
  --net=host \
  -v ${REPO_DIR}/config:/app/config:Z \
  -v ${DATA_DIR}:/app/data:Z \
  -v ${DOCS_DIR}:/docs:z \
  -e STAGING_DB=/app/data/staging.db \
  -e DOCS_DIR=/docs \
  -e PYTHONUNBUFFERED=1 \
  -e PYTHONLOGGING=WARNING \
  -e TZ=${TZ} \
  --health-cmd="curl -f http://localhost:8501/_stcore/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-start-period=60s \
  --health-retries=3 \
  localhost/peregrine:latest

echo ""
echo "Peregrine is starting up."
echo "  App: http://localhost:8501"
echo ""
echo "Check container health with:"
echo "  sudo podman ps"
echo "  sudo podman logs peregrine"
echo ""
echo "To register as a systemd service:"
echo "  sudo podman generate systemd --new --name peregrine \\"
echo "    | sudo tee /etc/systemd/system/peregrine.service"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now peregrine"
