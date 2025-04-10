#!/bin/sh

outfile="/tmp/grafana.deb"
download_base="https://dl.grafana.com/oss/release/"
case $1 in
   rpi)  package_file="grafana-rpi_10.4.2_armhf.deb"
       ;;
   aarch64) package_file="grafana_10.4.2_arm64.deb"
       ;;
   *) package_file="grafana_10.4.2_armhf.deb"
esac

# Primeiro tenta instalar o pacote .deb
if apt-get update && apt-get upgrade && apt-get install -y apt-utils musl || true; then
    echo "Tentando instalar via .deb: $package_file"
    if wget -O "$outfile" "${download_base}${package_file}"; then
        dpkg -i "$OUTFILE" || echo "Falha no dpkg, tentando fallback para tar.gz..."
        rm -f "$OUTFILE"
        if ! dpkg -s grafana >/dev/null 2>&1; then
            echo "Grafana não instalado corretamente, aplicando fallback para tar.gz"
            FALLBACK=true
        fi
    else
        echo "Falha no download do .deb, aplicando fallback"
        FALLBACK=true
    fi
else
    echo "musl não disponível, aplicando fallback"
    FALLBACK=true
fi


wget -O "${outfile}" "${download_base}${package_file}"
