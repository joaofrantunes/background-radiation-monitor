#!/bin/sh
set -eu

if [ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
    exit 0
fi

wget -q -O /dev/null http://127.0.0.1:2000/metrics
