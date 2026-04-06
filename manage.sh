#!/usr/bin/env bash
# manage.sh — Peregrine CLI wrapper
# A single entry point for all common operations.
# Usage: ./manage.sh <command> [options]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[peregrine]${NC} $*"; }
success() { echo -e "${GREEN}[peregrine]${NC} $*"; }
warn()    { echo -e "${YELLOW}[peregrine]${NC} $*"; }
error()   { echo -e "${RED}[peregrine]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROFILE="${PROFILE:-remote}"

# ── Usage ────────────────────────────────────────────────────────────────────
usage() {
    echo ""
    echo -e "  ${BLUE}Peregrine by Circuit Forge LLC${NC}"
    echo -e "  ${YELLOW}\"Don't be evil, for real and forever.\"${NC}"
    echo ""
    echo "  Usage: ./manage.sh <command> [--profile PROFILE]"
    echo ""
    echo "  Commands:"
    echo -e "    ${GREEN}setup${NC}               Install Docker/Podman + NVIDIA toolkit"
    echo -e "    ${GREEN}start${NC}               Start Peregrine (preflight → up)"
    echo -e "    ${GREEN}stop${NC}                Stop all services"
    echo -e "    ${GREEN}restart${NC}             Restart all services"
    echo -e "    ${GREEN}status${NC}              Show running containers"
    echo -e "    ${GREEN}logs [service]${NC}      Tail logs (default: app)"
    echo -e "    ${GREEN}update${NC}              Pull latest images + rebuild app"
    echo -e "    ${GREEN}preflight${NC}           Check ports + resources; write .env"
    echo -e "    ${GREEN}models${NC}              Check ollama models in config; pull any missing"
    echo -e "    ${GREEN}test${NC}                Run test suite"
    echo -e "    ${GREEN}e2e [mode]${NC}          Run E2E tests (mode: demo|cloud|local, default: demo)"
    echo -e "                        Set E2E_HEADLESS=false to run headed via Xvfb"
    echo -e "    ${GREEN}prepare-training${NC}    Extract cover letters → training JSONL"
    echo -e "    ${GREEN}finetune${NC}            Run LoRA fine-tune (needs GPU profile)"
    echo -e "    ${GREEN}clean${NC}               Remove containers, images, volumes (DESTRUCTIVE)"
    echo -e "    ${GREEN}open${NC}                Open the web UI in your browser"
    echo ""
    echo "  Profiles (set via --profile or PROFILE env var):"
    echo "    remote       API-only, no local inference (default)"
    echo "    cpu          Local Ollama inference on CPU"
    echo "    single-gpu   Ollama + Vision on GPU 0"
    echo "    dual-gpu     Ollama + Vision on GPU 0; GPU 1 set by DUAL_GPU_MODE"
    echo "                 DUAL_GPU_MODE=ollama  (default) ollama_research on GPU 1"
    echo "                 DUAL_GPU_MODE=vllm             vllm on GPU 1"
    echo "                 DUAL_GPU_MODE=mixed            both on GPU 1 (VRAM-split)"
    echo ""
    echo "  Examples:"
    echo "    ./manage.sh start"
    echo "    ./manage.sh start --profile cpu"
    echo "    ./manage.sh logs ollama"
    echo "    PROFILE=single-gpu ./manage.sh restart"
    echo ""
}

# ── Parse args ───────────────────────────────────────────────────────────────
CMD="${1:-help}"
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile|-p) PROFILE="$2"; shift 2 ;;
        --help|-h)    usage; exit 0 ;;
        *)            break ;;
    esac
done

SERVICE="${1:-app}"   # used by `logs` command

# ── Dependency guard ──────────────────────────────────────────────────────────
# Commands that delegate to make; others (status, logs, update, open, setup) run fine without it.
_MAKE_CMDS="start stop restart preflight test prepare-training finetune clean"
if [[ " $_MAKE_CMDS " == *" $CMD "* ]] && ! command -v make &>/dev/null; then
    error "'make' is not installed. Run:  ./manage.sh setup  then retry: ./manage.sh ${CMD}"
fi

# ── Commands ─────────────────────────────────────────────────────────────────
case "$CMD" in

    setup)
        info "Running dependency installer..."
        bash install.sh
        ;;

    preflight)
        info "Running preflight checks (PROFILE=${PROFILE})..."
        make preflight PROFILE="$PROFILE"
        ;;

    models)
        info "Checking ollama models..."
        conda run -n cf python scripts/preflight.py --models-only
        success "Model check complete."
        ;;

    start)
        info "Starting Peregrine (PROFILE=${PROFILE})..."
        make start PROFILE="$PROFILE"
        PORT="$(grep -m1 '^STREAMLIT_PORT=' .env 2>/dev/null | cut -d= -f2 || echo 8501)"
        success "Peregrine is up → http://localhost:${PORT}"
        ;;

    stop)
        info "Stopping all services..."
        make stop
        success "Stopped."
        ;;

    restart)
        info "Restarting (PROFILE=${PROFILE})..."
        make restart PROFILE="$PROFILE"
        PORT="$(grep -m1 '^STREAMLIT_PORT=' .env 2>/dev/null | cut -d= -f2 || echo 8501)"
        success "Peregrine restarted → http://localhost:${PORT}"
        ;;

    status)
        # Auto-detect compose engine same way Makefile does
        COMPOSE="$(command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 \
            && echo "docker compose" \
            || (command -v podman >/dev/null 2>&1 && echo "podman compose" || echo "podman-compose"))"
        $COMPOSE ps
        ;;

    logs)
        COMPOSE="$(command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 \
            && echo "docker compose" \
            || (command -v podman >/dev/null 2>&1 && echo "podman compose" || echo "podman-compose"))"
        info "Tailing logs for: ${SERVICE}"
        $COMPOSE logs -f "$SERVICE"
        ;;

    update)
        info "Pulling latest images and rebuilding app..."
        COMPOSE="$(command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 \
            && echo "docker compose" \
            || (command -v podman >/dev/null 2>&1 && echo "podman compose" || echo "podman-compose"))"
        $COMPOSE pull searxng ollama 2>/dev/null || true
        $COMPOSE build app web
        success "Update complete. Run './manage.sh restart' to apply."
        ;;

    test)
        info "Running test suite..."
        make test
        ;;

    prepare-training)
        info "Extracting training data from cover letter corpus..."
        make prepare-training
        ;;

    finetune)
        info "Starting fine-tune (PROFILE=${PROFILE})..."
        make finetune PROFILE="$PROFILE"
        ;;

    clean)
        warn "This will remove ALL Peregrine containers, images, and volumes."
        read -rp "Type 'yes' to confirm: " confirm
        [[ "$confirm" == "yes" ]] || { info "Cancelled."; exit 0; }
        make clean
        ;;

    open)
        PORT="$(grep -m1 '^STREAMLIT_PORT=' .env 2>/dev/null | cut -d= -f2 || echo 8501)"
        URL="http://localhost:${PORT}"
        info "Opening ${URL}"
        if command -v xdg-open &>/dev/null; then
            xdg-open "$URL"
        elif command -v open &>/dev/null; then
            open "$URL"
        else
            echo "$URL"
        fi
        ;;

    e2e)
        MODE="${2:-demo}"
        RESULTS_DIR="tests/e2e/results/${MODE}"
        mkdir -p "${RESULTS_DIR}"
        HEADLESS="${E2E_HEADLESS:-true}"
        if [ "$HEADLESS" = "false" ]; then
            RUNNER="xvfb-run --auto-servernum --server-args='-screen 0 1280x900x24'"
        else
            RUNNER=""
        fi
        info "Running E2E tests (mode=${MODE}, headless=${HEADLESS})..."
        $RUNNER conda run -n cf pytest tests/e2e/ \
            --mode="${MODE}" \
            --json-report \
            --json-report-file="${RESULTS_DIR}/report.json" \
            -v "${@:3}"
        ;;

    help|--help|-h)
        usage
        ;;

    *)
        error "Unknown command: ${CMD}. Run './manage.sh help' for usage."
        ;;

esac
