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

# GPU profiles on Podman require a CDI override (rootless Podman can't use driver: nvidia)
# Generate CDI spec first: sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
COMPOSE_FILES := -f compose.yml
ifneq (,$(findstring podman,$(COMPOSE)))
  ifneq (,$(findstring gpu,$(PROFILE)))
    COMPOSE_FILES := -f compose.yml -f compose.podman-gpu.yml
  endif
endif

setup:          ## Install dependencies (Docker or Podman + NVIDIA toolkit)
	@bash setup.sh

preflight:      ## Check ports + system resources; write .env
	@$(PYTHON) scripts/preflight.py

start: preflight  ## Preflight check then start Peregrine (PROFILE=remote|cpu|single-gpu|dual-gpu)
	$(COMPOSE) $(COMPOSE_FILES) --profile $(PROFILE) up -d

stop:           ## Stop all Peregrine services
	$(COMPOSE) down

restart: preflight  ## Preflight check then restart all services
	$(COMPOSE) down && $(COMPOSE) $(COMPOSE_FILES) --profile $(PROFILE) up -d

logs:           ## Tail app logs
	$(COMPOSE) logs -f app

test:           ## Run the test suite
	@$(PYTHON) -m pytest tests/ -v

prepare-training: ## Scan docs_dir for cover letters and build training JSONL
	$(COMPOSE) $(COMPOSE_FILES) run --rm app python scripts/prepare_training_data.py

finetune:       ## Fine-tune your personal cover letter model (run prepare-training first)
	@echo "Starting fine-tune (30-90 min on GPU, much longer on CPU)..."
	$(COMPOSE) $(COMPOSE_FILES) --profile $(PROFILE) run --rm finetune

clean:          ## Remove containers, images, and data volumes (DESTRUCTIVE)
	@echo "WARNING: This will delete all Peregrine containers and data."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	$(COMPOSE) down --rmi local --volumes

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
