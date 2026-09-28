FROM cloudflare/cloudflared:2026.9.1 AS cloudflared

FROM alpine:3.22

RUN addgroup -S cloudflared \
    && adduser -S -G cloudflared cloudflared

COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY entry.sh /usr/local/bin/entry.sh
COPY healthcheck.sh /usr/local/bin/healthcheck.sh

RUN chmod +x \
    /usr/local/bin/cloudflared \
    /usr/local/bin/entry.sh \
    /usr/local/bin/healthcheck.sh

USER cloudflared

ENTRYPOINT ["/usr/local/bin/entry.sh"]
