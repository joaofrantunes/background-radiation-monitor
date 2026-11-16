#!/bin/sh
set -eu

GRAFANA_DATA_DIR="${GF_PATHS_DATA:-/var/lib/grafana}"
GRAFANA_UID="$(id -u grafana)"
GRAFANA_GID="$(id -g grafana)"

mkdir -p "$GRAFANA_DATA_DIR"
chown -R "$GRAFANA_UID:$GRAFANA_GID" "$GRAFANA_DATA_DIR"

exec su-exec "$GRAFANA_UID:$GRAFANA_GID" /run.sh "$@"
