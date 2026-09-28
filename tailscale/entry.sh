#!/bin/sh
set -eu

state_dir="${TS_STATE_DIR:-/var/lib/tailscale}"
state_file="$state_dir/tailscaled.state"

if [ -z "${TS_AUTHKEY:-}" ] && [ ! -s "$state_file" ]; then
    echo "Tailscale disabled: TS_AUTHKEY is not set and no enrolled state exists."
    echo "Local access and the balena Public Device URL remain available."
    exec sleep 2147483647
fi

if [ -z "${TS_HOSTNAME:-}" ] && [ -n "${BALENA_DEVICE_UUID:-}" ]; then
    export TS_HOSTNAME="brm-${BALENA_DEVICE_UUID}"
fi

export TS_STATE_DIR="$state_dir"
export TS_AUTH_ONCE="${TS_AUTH_ONCE:-true}"
export TS_USERSPACE="${TS_USERSPACE:-false}"
export TS_ACCEPT_DNS="${TS_ACCEPT_DNS:-false}"

echo "Starting Tailscale peer."
echo "Once connected, open the dashboard through this peer's Tailscale IP on port 80."

exec /usr/local/bin/containerboot
