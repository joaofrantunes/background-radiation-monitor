#!/bin/sh
set -eu

outfile="/tmp/grafana.deb"
download_base="https://dl.grafana.com/oss/release/"

case "$1" in
    rpi)
        package_file="grafana-rpi_10.4.2_armhf.deb"
        ;;
    aarch64)
        package_file="grafana_10.4.2_arm64.deb"
        ;;
    *)
        echo "Unsupported balena architecture: $1" >&2
        exit 1
        ;;
esac

echo "Downloading Grafana package: $package_file"
wget -O "$outfile" "$download_base$package_file"
