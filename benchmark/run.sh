#!/bin/sh
# Runs the benchmark in the project's Docker image (Chromium, LibreOffice and poppler inside).
# Usage: benchmark/run.sh [--tools nativedeck,dom-to-pptx]
# With dom-to-pptx, `npm install dom-to-pptx` runs inside the container only: it is third-party code.
set -e
cd "$(dirname "$0")/.."
docker build -q -f docker/dev.Dockerfile -t nativedeck-dev docker >/dev/null
docker run --rm -v "$PWD":/src -w /src nativedeck-dev sh -c '
  uv sync -q
  case "$*" in *dom-to-pptx*) mkdir -p /opt/dom-to-pptx && (cd /opt/dom-to-pptx && npm install --silent dom-to-pptx);; esac
  /opt/venv/bin/python benchmark/run.py "$@"' sh "$@"
