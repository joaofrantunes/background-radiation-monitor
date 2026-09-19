#!/bin/sh
set -eu

exec grafana-server \
    -homepath /usr/share/grafana \
    -config /usr/share/grafana/conf/custom.ini
