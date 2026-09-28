#!/bin/sh
set -eu

state_present=0
if [ -s /var/lib/netbird/default.json ] || [ -s /var/lib/netbird/config.json ]; then
    state_present=1
fi

if [ -z "${NB_SETUP_KEY:-}" ] && [ "$state_present" -eq 0 ]; then
    echo "NetBird disabled: NB_SETUP_KEY is not set and no enrolled state exists."
    echo "Local access and the balena Public Device URL remain available."
    exec sleep 2147483647
fi

if [ -z "${NB_HOSTNAME:-}" ] && [ -n "${BALENA_DEVICE_UUID:-}" ]; then
    export NB_HOSTNAME="brm-${BALENA_DEVICE_UUID}"
fi

echo "Starting NetBird peer."
echo "Once connected, open the dashboard through this peer's NetBird IP on port 80."

exec /usr/local/bin/netbird-entrypoint.sh
