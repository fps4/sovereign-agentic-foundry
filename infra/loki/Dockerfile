FROM grafana/loki:latest

USER root

COPY loki-config.yaml /etc/loki/config/loki.yaml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
