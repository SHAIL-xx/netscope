#!/usr/bin/env bash
# Start the local Floci AWS emulator (if it is not already running) and wait until it answers.
# Usage: bash infra/floci-up.sh
set -euo pipefail

NAME=floci-netscope
PORT=4566
WAIT_SECONDS="${WAIT_SECONDS:-30}"

if [ -n "$(docker ps -q --filter "name=^${NAME}$")" ]; then
  echo "$NAME is already running"
elif [ -n "$(docker ps -aq --filter "name=^${NAME}$")" ]; then
  echo "starting the existing $NAME container"
  docker start "$NAME" > /dev/null
else
  echo "creating $NAME (listens on 127.0.0.1 only)"
  docker run -d --name "$NAME" -p "127.0.0.1:${PORT}:4566" \
    -v /var/run/docker.sock:/var/run/docker.sock -u root floci/floci:latest > /dev/null
fi

for _ in $(seq 1 "$WAIT_SECONDS"); do
  if curl -s -o /dev/null "http://localhost:${PORT}/"; then
    echo "Floci is answering on port ${PORT}"
    exit 0
  fi
  sleep 1
done

echo "Floci did not answer within ${WAIT_SECONDS} seconds. Check: docker logs --tail 30 ${NAME}" >&2
exit 1