FROM netbirdio/netbird:0.79.0

COPY entry.sh /usr/local/bin/brm-netbird-entrypoint.sh
COPY healthcheck.sh /usr/local/bin/brm-netbird-healthcheck.sh

RUN chmod +x \
    /usr/local/bin/brm-netbird-entrypoint.sh \
    /usr/local/bin/brm-netbird-healthcheck.sh

ENTRYPOINT ["/usr/local/bin/brm-netbird-entrypoint.sh"]
