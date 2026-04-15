#!/bin/sh
# Start the cf-orch agent. Adds --advertise-host only when CF_ORCH_ADVERTISE_HOST is set.
set -e

ARGS="--coordinator ${CF_ORCH_COORDINATOR_URL:-http://host.docker.internal:7700} \
      --node-id ${CF_ORCH_NODE_ID:-peregrine} \
      --host 0.0.0.0 \
      --port ${CF_ORCH_AGENT_PORT:-7701}"

if [ -n "${CF_ORCH_ADVERTISE_HOST}" ]; then
    ARGS="$ARGS --advertise-host ${CF_ORCH_ADVERTISE_HOST}"
fi

exec cf-orch agent $ARGS
