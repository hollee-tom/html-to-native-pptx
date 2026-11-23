#!/bin/sh
# Run a command inside the project's dev image, with the project mounted at /src and its
# virtualenv synced: docker/dev.sh pytest -q
set -e
cd "$(dirname "$0")/.."
docker build -q -f docker/dev.Dockerfile -t nativedeck-dev docker >/dev/null
docker run --rm -v "$PWD":/src -w /src -e NATIVEDECK_CHROMIUM nativedeck-dev sh -c 'uv sync -q && . /opt/venv/bin/activate && "$@"' sh "$@"
