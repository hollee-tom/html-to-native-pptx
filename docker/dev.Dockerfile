# Everything that needs a browser or LibreOffice runs here: the tests, the CLI and the benchmark.
# The Playwright base image carries the Chromium that matches the pinned Playwright release.
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      libreoffice-impress poppler-utils fontconfig fonts-liberation fonts-dejavu-core nodejs npm >/dev/null \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --quiet uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy
WORKDIR /src
