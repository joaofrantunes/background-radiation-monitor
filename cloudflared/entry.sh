#!/bin/sh
set -eu

if [ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
    echo "Cloudflare Tunnel disabled: CLOUDFLARE_TUNNEL_TOKEN is not set."
    echo "balena Public Device URL and local Nginx access remain available."
    exec sleep 2147483647
fi

loglevel="${CLOUDFLARE_LOGLEVEL:-info}"

echo "Starting Cloudflare Tunnel."
echo "Origin route must point to http://web:80 in the Cloudflare dashboard."

exec /usr/local/bin/cloudflared \
    --no-autoupdate \
    tunnel \
    --metrics 0.0.0.0:2000 \
    --loglevel "$loglevel" \
    run \
    --token "$CLOUDFLARE_TUNNEL_TOKEN"
