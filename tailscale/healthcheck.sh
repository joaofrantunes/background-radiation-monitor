#!/bin/sh
set -eu

state_dir="${TS_STATE_DIR:-/var/lib/tailscale}"
state_file="$state_dir/tailscaled.state"

if [ -z "${TS_AUTHKEY:-}" ] && [ ! -s "$state_file" ]; then
    exit 0
fi

exec /usr/local/bin/tailscale status --json
