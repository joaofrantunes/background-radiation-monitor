#!/bin/sh
set -eu

GRAFANA_DATA_DIR="${GF_PATHS_DATA:-/var/lib/grafana}"

mkdir -p "$GRAFANA_DATA_DIR"
chown -R grafana:grafana "$GRAFANA_DATA_DIR"

exec su-exec grafana /run.sh "$@"
