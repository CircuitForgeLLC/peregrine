# Makefile — Peregrine convenience targets
# Usage: make <target>

.PHONY: setup preflight start stop restart logs test prepare-training finetune clean help

PROFILE ?= remote
PYTHON  ?= python3

# Auto-detect container engine: prefer docker compose, fall back to podman
COMPOSE ?= $(shell \
  command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 \
  && echo "docker compose" \
  || (command -v podman >/dev/null 2>&1 \
      && podman compose version >/dev/null 2>&1 \
      && echo "podman compose" \
      || echo "podman-compose"))

# GPU profiles require an overlay for NVIDIA device reservations.
# Docker uses deploy.resources (compose.gpu.yml); Podman uses CDI device specs (compose.podman-gpu.yml).
# Generate CDI spec for Podman first: sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
#
# NOTE: When explicit -f flags are used, Docker Compose does NOT auto-detect
# compose.override.yml. We must include it explicitly when present.
OVERRIDE_FILE := $(wildcard compose.override.yml)
COMPOSE_OVERRIDE := $(if $(OVERRIDE_FILE),-f compose.override.yml,)
DUAL_GPU_MODE ?= $(shell grep -m1 '^DUAL_GPU_MODE=' .env 2>/dev/null | cut -d= -f2 || echo ollama)

COMPOSE_FILES := -f compose.yml $(COMPOSE_OVERRIDE)
ifneq (,$(findstring podman,$(COMPOSE)))
  ifneq (,$(findstring gpu,$(PROFILE)))
    COMPOSE_FILES := -f compose.yml $(COMPOSE_OVERRIDE) -f compose.podman-gpu.yml
  endif
else
  ifneq (,$(findstring gpu,$(PROFILE)))
    COMPOSE_FILES := -f compose.yml $(COMPOSE_OVERRIDE) -f compose.gpu.yml
  endif
endif
ifeq ($(PROFILE),dual-gpu)
  COMPOSE_FILES += --profile dual-gpu-$(DUAL_GPU_MODE)
endif

# 'remote' means base services only — no services are tagged 'remote' in compose.yml,
# so --profile remote is a no-op with Docker and a fatal error on old podman-compose.
# Only pass --profile for profiles that actually activate optional services.
PROFILE_ARG := $(if $(filter remote,$(PROFILE)),,--profile $(PROFILE))

setup:          ## Install dependencies (Docker or Podman + NVIDIA toolkit)
	@bash setup.sh

preflight:      ## Check ports + system resources; write .env
	@$(PYTHON) scripts/preflight.py

start: preflight  ## Preflight check then start Peregrine (PROFILE=remote|cpu|single-gpu|dual-gpu)
	$(COMPOSE) $(COMPOSE_FILES) $(PROFILE_ARG) up -d

stop:           ## Stop all Peregrine services
	$(COMPOSE) down

restart:  ## Stop services, re-run preflight (ports now free), then start
	$(COMPOSE) down
	@$(PYTHON) scripts/preflight.py
	$(COMPOSE) $(COMPOSE_FILES) $(PROFILE_ARG) up -d

logs:           ## Tail app logs
	$(COMPOSE) logs -f app

test:           ## Run the test suite
	@$(PYTHON) -m pytest tests/ -v

prepare-training: ## Scan docs_dir for cover letters and build training JSONL
	$(COMPOSE) $(COMPOSE_FILES) run --rm app python scripts/prepare_training_data.py

finetune:       ## Fine-tune your personal cover letter model (run prepare-training first)
	@echo "Starting fine-tune (30-90 min on GPU, much longer on CPU)..."
	$(COMPOSE) $(COMPOSE_FILES) -f compose.gpu.yml --profile finetune run --rm finetune

clean:          ## Remove containers, images, and data volumes (DESTRUCTIVE)
	@echo "WARNING: This will delete all Peregrine containers and data."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	$(COMPOSE) down --rmi local --volumes

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
