FROM tailscale/tailscale:v1.102.5

COPY entry.sh /usr/local/bin/brm-tailscale-entrypoint.sh
COPY healthcheck.sh /usr/local/bin/brm-tailscale-healthcheck.sh

RUN chmod +x \
    /usr/local/bin/brm-tailscale-entrypoint.sh \
    /usr/local/bin/brm-tailscale-healthcheck.sh

ENTRYPOINT ["/usr/local/bin/brm-tailscale-entrypoint.sh"]
