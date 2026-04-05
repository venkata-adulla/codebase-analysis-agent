#!/usr/bin/env bash
# Wait for TCP reachability of Postgres, Neo4j Bolt, and Redis before app startup.
# Configure hosts/ports via environment (defaults suit docker-compose service names).
set -euo pipefail

POSTGRES_WAIT_HOST="${POSTGRES_WAIT_HOST:-postgres}"
POSTGRES_WAIT_PORT="${POSTGRES_WAIT_PORT:-5432}"
NEO4J_WAIT_HOST="${NEO4J_WAIT_HOST:-neo4j}"
NEO4J_WAIT_PORT="${NEO4J_WAIT_PORT:-7687}"
REDIS_WAIT_HOST="${REDIS_WAIT_HOST:-redis}"
REDIS_WAIT_PORT="${REDIS_WAIT_PORT:-6379}"
WAIT_TIMEOUT_SEC="${WAIT_TIMEOUT_SEC:-60}"

wait_tcp() {
  local host="$1"
  local port="$2"
  local name="$3"
  local deadline=$((SECONDS + WAIT_TIMEOUT_SEC))

  echo "waiting for ${name} (${host}:${port})..."
  while true; do
    if [ "${SECONDS}" -ge "${deadline}" ]; then
      echo "ERROR: ${name} unreachable at ${host}:${port} after ${WAIT_TIMEOUT_SEC}s" >&2
      exit 1
    fi
    if nc -z -w 2 "${host}" "${port}" 2>/dev/null; then
      echo "${name} ready"
      return 0
    fi
    sleep 1
  done
}

wait_tcp "${POSTGRES_WAIT_HOST}" "${POSTGRES_WAIT_PORT}" "postgres"
wait_tcp "${NEO4J_WAIT_HOST}" "${NEO4J_WAIT_PORT}" "neo4j"
wait_tcp "${REDIS_WAIT_HOST}" "${REDIS_WAIT_PORT}" "redis"

echo "all dependencies reachable"
