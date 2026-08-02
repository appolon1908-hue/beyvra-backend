FROM python:3.11-slim-bookworm

WORKDIR /app/

# # Install system dependencies
RUN apt-get update \
    && apt-get upgrade -y \
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
    && rm -rf /var/lib/apt/lists/*

# Create logs directory
RUN mkdir -p /logs

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

RUN chmod +x /app/worker-entrypoint.sh
RUN chmod +x /app/beat-entrypoint.sh
RUN chmod +x /app/web-init-prod.sh
