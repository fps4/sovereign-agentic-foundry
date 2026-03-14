#!/bin/sh
set -eu

POSITIONS_DIR=/run/promtail
mkdir -p "$POSITIONS_DIR"
chown -R 0:0 "$POSITIONS_DIR" 2>/dev/null || true

exec /usr/bin/promtail "$@"
