#!/usr/bin/env bash
# scripts/manage-vllm.sh — manage the vLLM inference server
# Usage: bash scripts/manage-vllm.sh [start [model]|stop|restart [model]|status|logs|list]

set -euo pipefail

VLLM_BIN="${VLLM_BIN:-python3}"
MODEL_DIR="${VLLM_MODELS_DIR:-${HOME}/models/vllm}"
PID_FILE="/tmp/vllm-server.pid"
LOG_FILE="/tmp/vllm-server.log"
MODEL_FILE="/tmp/vllm-server.model"
PORT=8000
GPU=1

_list_model_names() {
    if [[ -d "$MODEL_DIR" ]]; then
        find "$MODEL_DIR" -maxdepth 1 -mindepth 1 -type d -printf '%f\n' 2>/dev/null | sort
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

start() {
    local model_name="${1:-}"

    if [[ -z "$model_name" ]]; then
        model_name=$(_list_model_names | head -1)
        if [[ -z "$model_name" ]]; then
            echo "No models found in $MODEL_DIR"
            exit 1
        fi
    fi

    local model_path
    if [[ "$model_name" == /* ]]; then
        model_path="$model_name"
        model_name=$(basename "$model_path")
    else
        model_path="$MODEL_DIR/$model_name"
    fi

    if [[ ! -d "$model_path" ]]; then
        echo "Model not found: $model_path"
        exit 1
    fi

    if is_running; then
        echo "Already running (PID $(cat "$PID_FILE")). Use 'restart' to reload."
        return 0
    fi

    echo "Starting vLLM with model: $model_name (GPU $GPU, port $PORT)…"
    echo "$model_name" > "$MODEL_FILE"

    # Ouro LoopLM uses total_ut_steps=4 which multiplies KV cache by 4x vs a standard
    # transformer. On 8 GiB GPUs: 1.4B models support ~4096 tokens; 2.6B only ~928.
    CUDA_VISIBLE_DEVICES="$GPU" "$VLLM_BIN" -m vllm.entrypoints.openai.api_server \
        --model "$model_path" \
        --trust-remote-code \
        --max-model-len 3072 \
        --gpu-memory-utilization 0.75 \
        --enforce-eager \
        --max-num-seqs 8 \
        --port "$PORT" \
        > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 3

    if is_running; then
        echo "Started (PID $(cat "$PID_FILE")). Logs: $LOG_FILE"
    else
        echo "Failed to start. Check logs: $LOG_FILE"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE" "$MODEL_FILE"
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
    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE" "$MODEL_FILE"
    echo "Stopped."
}

restart() {
    local model_name="${1:-}"
    stop
    sleep 1
    start "$model_name"
}

status() {
    if is_running; then
        local model=""
        if [[ -f "$MODEL_FILE" ]]; then
            model=" — model: $(cat "$MODEL_FILE")"
        fi
        echo "Running (PID $(cat "$PID_FILE")) on http://localhost:$PORT$model"
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

list() {
    echo "Available models in $MODEL_DIR:"
    _list_model_names | while read -r name; do
        echo "  - $name"
    done
}

CMD="${1:-help}"
case "$CMD" in
    start)   start "${2:-}" ;;
    stop)    stop ;;
    restart) restart "${2:-}" ;;
    status)  status ;;
    logs)    logs ;;
    list)    list ;;
    *)
        echo "Usage: bash scripts/manage-vllm.sh [start [model]|stop|restart [model]|status|logs|list]"
        echo ""
        echo "  start [model]    Start vLLM with the specified model (default: first in $MODEL_DIR)"
        echo "  stop             Stop the running vLLM server"
        echo "  restart [model]  Stop then start (pass a new model name to swap)"
        echo "  status           Show whether it's running and which model is loaded"
        echo "  logs             Tail the last 50 lines of the log"
        echo "  list             List available models"
        echo ""
        echo "  GPU:  $GPU (CUDA_VISIBLE_DEVICES)"
        echo "  Port: $PORT"
        ;;
esac
