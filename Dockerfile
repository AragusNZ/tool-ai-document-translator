FROM python:3.12-slim-bookworm@sha256:76d4b7b6305788c6b4c6a19d6a22a3921bf802e9af4d5e1e5bd771208dba74bf

LABEL org.opencontainers.image.source=https://github.com/AragusNZ/tool-ai-document-translator

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    tesseract-ocr \
    tesseract-ocr-eng \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src

ARG WITH_LITEPARSE=0
RUN pip install --upgrade pip && \
    pip install ".[monitoring,openai,anthropic,google]" && \
    if [ "$WITH_LITEPARSE" = "1" ]; then pip install ".[extract-liteparse]"; fi

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /runs /input \
    && chown -R appuser:appuser /app /runs /input

USER appuser

WORKDIR /runs

ENTRYPOINT ["document-translator"]
CMD ["--help"]
