#!/usr/bin/env bash
# GET /health against a running sidecar. Set USERNAME_DISCOVERY_API_KEY first.
set -euo pipefail

BASE="${USERNAME_DISCOVERY_URL:-http://127.0.0.1:8095}"
KEY="${USERNAME_DISCOVERY_API_KEY:-}"

if [[ -z "$KEY" ]]; then
  echo "smoke_health: set USERNAME_DISCOVERY_API_KEY" >&2
  exit 1
fi

curl -fsS -H "X-API-Key: ${KEY}" "${BASE%/}/health"
echo
