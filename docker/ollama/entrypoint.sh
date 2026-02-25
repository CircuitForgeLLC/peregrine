#!/usr/bin/env bash
# Start Ollama server and pull a default model if none are present
ollama serve &
sleep 5
if [ -z "$(ollama list 2>/dev/null | tail -n +2)" ]; then
    MODEL="${DEFAULT_OLLAMA_MODEL:-llama3.2:3b}"
    echo "No models found — pulling $MODEL..."
    ollama pull "$MODEL"
fi
wait
