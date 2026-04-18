#!/usr/bin/env bash
set -euo pipefail

GRIST_PORT=${GRIST_PORT:-8484}
GRIST_DATA_DIR=${GRIST_DATA_DIR:-"$HOME/grist"}
GRIST_EMAIL=${GRIST_DEFAULT_EMAIL:-"admin@localhost"}
GRIST_SECRET=${GRIST_SESSION_SECRET:-"c0136d94dbe8609d510f08bdea390694cd45ff50"}

mkdir -p "$GRIST_DATA_DIR"

echo "Starting Grist on 0.0.0.0:${GRIST_PORT}"
echo "Data directory: ${GRIST_DATA_DIR}"
echo "Admin email:    ${GRIST_EMAIL}"

docker run \
  --name grist \
  --rm \
  -p "0.0.0.0:${GRIST_PORT}:8484" \
  -v "${GRIST_DATA_DIR}:/persist" \
  -e GRIST_SESSION_SECRET="${GRIST_SECRET}" \
  -e GRIST_DEFAULT_EMAIL="${GRIST_EMAIL}" \
  -e APP_HOME_URL="http://0.0.0.0:${GRIST_PORT}" \
  -d \
  gristlabs/grist
