FROM grafana/promtail:latest

USER root

COPY promtail-config.yaml /etc/promtail/config.yml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
