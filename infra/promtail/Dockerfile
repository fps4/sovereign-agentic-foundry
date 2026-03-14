FROM grafana/promtail:latest

USER root

# Copy to the default location Promtail's built-in entrypoint already reads
COPY promtail-config.yaml /etc/promtail/config.yml
