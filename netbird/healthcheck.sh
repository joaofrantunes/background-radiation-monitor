#!/bin/sh
set -eu

if [ -z "${NB_SETUP_KEY:-}" ]     && [ ! -s /var/lib/netbird/default.json ]     && [ ! -s /var/lib/netbird/config.json ]; then
    exit 0
fi

exec /usr/local/bin/netbird status --check live
