#!/usr/bin/env bash
set -euo pipefail

WEBUI_HOST=${WEBUI_HOST:-0.0.0.0}
WEBUI_PORT=${WEBUI_PORT:-8000}

# Load .env if present (for GRIST_SERVER, GRIST_API_KEY, VLLM_BASE_URL, etc.)
if [[ -f ".env" ]]; then
  set -a
  source .env
  set +a
  echo "[webui] Loaded .env"
fi

echo "[webui] Starting grist-excel Web UI"
echo "[webui] Host:        ${WEBUI_HOST}:${WEBUI_PORT}"
echo "[webui] Grist:       ${GRIST_SERVER:-http://localhost:8484}"
echo "[webui] vLLM:        ${VLLM_BASE_URL:-http://172.17.0.1:30000}"
echo ""
echo "[webui] Open http://localhost:${WEBUI_PORT} in your browser"
echo ""

exec uv run uvicorn webui.server:app \
  --host "${WEBUI_HOST}" \
  --port "${WEBUI_PORT}" \
  --reload
