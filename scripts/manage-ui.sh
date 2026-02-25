#!/usr/bin/env bash
# scripts/manage-ui.sh — manage the Streamlit job-seeker web UI
# Usage: bash scripts/manage-ui.sh [start|stop|restart|status|logs]

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STREAMLIT_BIN="/devl/miniconda3/envs/job-seeker/bin/streamlit"
APP_ENTRY="$REPO_DIR/app/app.py"
PID_FILE="$REPO_DIR/.streamlit.pid"
LOG_FILE="$REPO_DIR/.streamlit.log"
PORT="${STREAMLIT_PORT:-8501}"

start() {
    if is_running; then
        echo "Already running (PID $(cat "$PID_FILE")). Use 'restart' to reload."
        return 0
    fi

    echo "Starting Streamlit on http://localhost:$PORT …"
    "$STREAMLIT_BIN" run "$APP_ENTRY" \
        --server.port "$PORT" \
        --server.headless true \
        --server.fileWatcherType none \
        > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if is_running; then
        echo "Started (PID $(cat "$PID_FILE")). Logs: $LOG_FILE"
    else
        echo "Failed to start. Check logs: $LOG_FILE"
        tail -20 "$LOG_FILE"
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
    echo "Stopping PID $PID …"
    kill "$PID" 2>/dev/null || true
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "Stopped."
}

restart() {
    stop
    sleep 1
    start
}

status() {
    if is_running; then
        echo "Running (PID $(cat "$PID_FILE")) on http://localhost:$PORT"
    else
        echo "Not running."
    fi
}

logs() {
    if [[ -f "$LOG_FILE" ]]; then
        tail -50 "$LOG_FILE"
    else
        echo "No log file found at $LOG_FILE"
    fi
}

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

CMD="${1:-help}"
case "$CMD" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    logs)    logs ;;
    *)
        echo "Usage: bash scripts/manage-ui.sh [start|stop|restart|status|logs]"
        echo ""
        echo "  start    Start the Streamlit UI (default port: $PORT)"
        echo "  stop     Stop the running UI"
        echo "  restart  Stop then start"
        echo "  status   Show whether it's running"
        echo "  logs     Tail the last 50 lines of the log"
        echo ""
        echo "  STREAMLIT_PORT=8502 bash scripts/manage-ui.sh start  (custom port)"
        ;;
esac
