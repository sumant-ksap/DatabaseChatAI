#!/bin/sh
set -e

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:31b-cloud}"
PORT="${PORT:-10000}"

mkdir -p "${OLLAMA_MODELS:-/root/.ollama/models}"

ollama serve &

echo "Waiting for Ollama to become ready..."
until curl -sf "${OLLAMA_BASE_URL}/api/tags" >/dev/null 2>&1; do
  sleep 1
done

echo "Pulling model ${OLLAMA_MODEL} (skips if already present on disk)..."
ollama pull "${OLLAMA_MODEL}"

echo "Starting web app on port ${PORT}..."
exec gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 120 app:app
