#!/usr/bin/env bash
# scripts/manage-vision.sh — manage the moondream2 vision service
# Usage: bash scripts/manage-vision.sh start|stop|restart|status|logs
#
# First-time setup:
#   conda env create -f scripts/vision_service/environment.yml
#
# On first start, moondream2 is downloaded from HuggingFace (~1.8GB).
# Model stays resident in memory between requests.

set -euo pipefail

CONDA_ENV="job-seeker-vision"
UVICORN_BIN="/devl/miniconda3/envs/${CONDA_ENV}/bin/uvicorn"
PID_FILE="/tmp/vision-service.pid"
LOG_FILE="/tmp/vision-service.log"
PORT=8002
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

start() {
    if is_running; then
        echo "Already running (PID $(cat "$PID_FILE"))."
        return 0
    fi

    if [[ ! -f "$UVICORN_BIN" ]]; then
        echo "ERROR: conda env '$CONDA_ENV' not found."
        echo "Install with: conda env create -f scripts/vision_service/environment.yml"
        exit 1
    fi

    echo "Starting vision service (moondream2) on port $PORT…"
    cd "$REPO_ROOT"
    PYTHONPATH="$REPO_ROOT" "$UVICORN_BIN" \
        scripts.vision_service.main:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if is_running; then
        echo "Started (PID $(cat "$PID_FILE")). Logs: $LOG_FILE"
        echo "Health: http://localhost:$PORT/health"
    else
        echo "Failed to start. Check logs: $LOG_FILE"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if ! is_running; then
        echo "Not running."
        rm -f "$PID_FILE"
        return 0
    fi
    PID=$(cat "$PID_FILE")
    echo "Stopping PID $PID…"
    kill "$PID" 2>/dev/null || true
    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "Stopped."
}

restart() { stop; sleep 1; start; }

status() {
    if is_running; then
        echo "Running (PID $(cat "$PID_FILE")) — http://localhost:$PORT"
        curl -s "http://localhost:$PORT/health" | python3 -m json.tool 2>/dev/null || true
    else
        echo "Not running."
    fi
}

logs() {
    if [[ -f "$LOG_FILE" ]]; then
        tail -50 "$LOG_FILE"
    else
        echo "No log file at $LOG_FILE"
    fi
}

CMD="${1:-help}"
case "$CMD" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    logs)    logs ;;
    *)
        echo "Usage: bash scripts/manage-vision.sh start|stop|restart|status|logs"
        echo ""
        echo "  Manages the moondream2 vision service on port $PORT."
        echo "  First-time setup: conda env create -f scripts/vision_service/environment.yml"
        ;;
esac
