# Makefile — Peregrine convenience targets
# Usage: make <target>

.PHONY: setup preflight start stop restart logs test clean help

PROFILE ?= remote
PYTHON  ?= python3

setup:          ## Install dependencies (Docker, NVIDIA toolkit)
	@bash setup.sh

preflight:      ## Check ports + system resources; write .env
	@$(PYTHON) scripts/preflight.py

start: preflight  ## Preflight check then start Peregrine (PROFILE=remote|cpu|single-gpu|dual-gpu)
	docker compose --profile $(PROFILE) up -d

stop:           ## Stop all Peregrine services
	docker compose down

restart: preflight  ## Preflight check then restart all services
	docker compose down && docker compose --profile $(PROFILE) up -d

logs:           ## Tail app logs
	docker compose logs -f app

test:           ## Run the test suite
	$(PYTHON) -m pytest tests/ -v

clean:          ## Remove containers, images, and data volumes (DESTRUCTIVE)
	@echo "WARNING: This will delete all Peregrine containers and data."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	docker compose down --rmi local --volumes

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
