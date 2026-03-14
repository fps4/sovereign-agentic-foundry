FROM grafana/loki:latest

USER root

# Copy to the default location Loki's built-in entrypoint already reads
COPY loki-config.yaml /etc/loki/local-config.yaml
