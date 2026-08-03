FROM python:3.11-slim-bookworm

WORKDIR /app/

# # Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    gcc \
    libc-dev \
    libffi-dev \
    libpq-dev \
    postgresql-client \
    redis-tools \
    netcat-openbsd \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --create-home app

# Create logs directory
RUN mkdir -p /logs && chown app:app /logs

# Install python dependencies
COPY requirements.txt /app/requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --upgrade pip wheel setuptools \
    && pip install --no-cache-dir --requirement /app/requirements.txt \
    && pip uninstall --yes pip setuptools wheel

# Copy the source code
COPY . /app/

COPY worker-entrypoint.sh /app/worker-entrypoint.sh
COPY beat-entrypoint.sh /app/beat-entrypoint.sh

RUN chmod +x /app/worker-entrypoint.sh /app/beat-entrypoint.sh /app/web-init-prod.sh \
    && chown -R app:app /app

ARG VCS_REF=unknown
ARG BUILD_VERSION=unreleased
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.source="https://github.com/appolon1908-hue/trading-backend" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$BUILD_VERSION" \
      org.opencontainers.image.created="$BUILD_DATE"

USER app
