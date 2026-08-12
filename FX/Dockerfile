ARG PYTHON_IMAGE=python:3.11-alpine3.22

FROM ${PYTHON_IMAGE} AS builder

RUN apk add --no-cache --virtual .build-deps \
        build-base \
        libffi-dev \
        linux-headers \
        postgresql-dev

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip wheel setuptools \
    && pip install --no-cache-dir --requirement /tmp/requirements.txt \
    && sed -i '/    Example input:/,/    :param keydata:/{ /    Example input:/!{ /    :param keydata:/!d; }; }' /opt/venv/lib/python3.11/site-packages/autobahn/wamp/cryptosign.py \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf '{}' + \
    && find /opt/venv -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete \
    && pip uninstall --yes pip setuptools wheel \
    && rm -rf /root/.cache /tmp/requirements.txt

FROM ${PYTHON_IMAGE} AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/

RUN apk upgrade --no-cache \
    && python -m pip uninstall --yes pip setuptools wheel \
    && rm -rf /root/.cache \
    && addgroup --system app \
    && adduser --system --ingroup app --home /home/app app \
    && mkdir -p /logs \
    && chown app:app /logs

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . /app/

RUN chmod +x /app/worker-entrypoint.sh /app/beat-entrypoint.sh /app/web-init-prod.sh

ARG VCS_REF=unknown
ARG BUILD_VERSION=unreleased
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.source="https://github.com/appolon1908-hue/trading-backend" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$BUILD_VERSION" \
      org.opencontainers.image.created="$BUILD_DATE"

USER app
