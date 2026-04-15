# Peregrine → xanderland.tv Setup Handoff

**Written from:** dev machine (CircuitForge dev env)
**Target:** xanderland.tv (beta tester, rootful Podman + systemd)
**Date:** 2026-02-27

---

## What we're doing

Getting Peregrine running on the beta tester's server as a Podman container managed by systemd. He already runs SearXNG and other services in the same style — rootful Podman with `--net=host`, `--restart=unless-stopped`, registered as systemd units.

The script `podman-standalone.sh` in the repo root handles the container setup.

---

## Step 1 — Get the repo onto xanderland.tv

From navi (or directly if you have a route):

```bash
ssh xanderland.tv "sudo git clone <repo-url> /opt/peregrine"
```

Or if it's already there, just pull:

```bash
ssh xanderland.tv "cd /opt/peregrine && sudo git pull"
```

---

## Step 2 — Verify /opt/peregrine looks right

```bash
ssh xanderland.tv "ls /opt/peregrine"
```

Expect to see: `Dockerfile`, `compose.yml`, `manage.sh`, `podman-standalone.sh`, `config/`, `app/`, `scripts/`, etc.

---

## Step 3 — Config

```bash
ssh xanderland.tv
cd /opt/peregrine
sudo mkdir -p data
sudo cp config/llm.yaml.example config/llm.yaml
sudo cp config/notion.yaml.example config/notion.yaml   # only if he wants Notion sync
```

Then edit `config/llm.yaml` and set `searxng_url` to his existing SearXNG instance
(default is `http://localhost:8888` — confirm his actual port).

He won't need Anthropic/OpenAI keys to start — the setup wizard lets him pick local Ollama
or whatever he has running.

---

## Step 4 — Fix DOCS_DIR in the script

The script defaults `DOCS_DIR=/Library/Documents/JobSearch` which is the original user's path.
Update it to wherever his job search documents actually live, or a placeholder empty dir:

```bash
sudo mkdir -p /opt/peregrine/docs   # placeholder if he has no docs yet
```

Then edit the script:
```bash
sudo sed -i 's|DOCS_DIR=.*|DOCS_DIR=/opt/peregrine/docs|' /opt/peregrine/podman-standalone.sh
```

---

## Step 5 — Build the image

```bash
ssh xanderland.tv "cd /opt/peregrine && sudo podman build -t localhost/peregrine:latest ."
```

Takes a few minutes on first run (downloads python:3.11-slim, installs deps).

---

## Step 6 — Run the script

```bash
ssh xanderland.tv "sudo bash /opt/peregrine/podman-standalone.sh"
```

This starts a single container (`peregrine`) with `--net=host` and `--restart=unless-stopped`.
SearXNG is NOT included — his existing instance is used.

Verify it came up:
```bash
ssh xanderland.tv "sudo podman ps | grep peregrine"
ssh xanderland.tv "sudo podman logs peregrine"
```

Health check endpoint: `http://xanderland.tv:8501/_stcore/health`

---

## Step 7 — Register as a systemd service

```bash
ssh xanderland.tv
sudo podman generate systemd --new --name peregrine \
  | sudo tee /etc/systemd/system/peregrine.service
sudo systemctl daemon-reload
sudo systemctl enable --now peregrine
```

Confirm:
```bash
sudo systemctl status peregrine
```

---

## Step 8 — First-run wizard

Open `http://xanderland.tv:8501` in a browser.

The setup wizard (page 0) will gate the app until `config/user.yaml` is created.
He'll fill in his profile — name, resume, LLM backend preferences. This writes
`config/user.yaml` and unlocks the rest of the UI.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Container exits immediately | `sudo podman logs peregrine` — usually a missing config file |
| Port 8501 already in use | `sudo ss -tlnp \| grep 8501` — something else on that port |
| SearXNG not reachable | Confirm `searxng_url` in `config/llm.yaml` and that JSON format is enabled in SearXNG settings |
| Wizard loops / won't save | `config/` volume mount permissions — `sudo chown -R 1000:1000 /opt/peregrine/config` |

---

## To update Peregrine later

```bash
cd /opt/peregrine
sudo git pull
sudo podman build -t localhost/peregrine:latest .
sudo podman restart peregrine
```

No need to touch the systemd unit — it launches fresh via `--new` in the generate step.
