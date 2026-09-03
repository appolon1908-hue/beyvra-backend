ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.29-alpine
FROM ${NGINX_IMAGE}

ARG VCS_REF=unknown
ARG BUILD_VERSION=unreleased
ARG BUILD_DATE=unknown

USER root

RUN rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /etc/nginx/templates \
    && chown -R nginx:nginx /etc/nginx/conf.d /etc/nginx/templates \
    && chmod -R u=rwX,go=rX /etc/nginx/conf.d /etc/nginx/templates

COPY --chown=root:root nginx.conf /etc/nginx/nginx.conf
COPY --chown=root:root nginx.prod.conf.template \
    /etc/nginx/templates/default.conf.template

LABEL org.opencontainers.image.source="https://github.com/appolon1908-hue/beyvra-backend" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$BUILD_VERSION" \
      org.opencontainers.image.created="$BUILD_DATE" \
      org.opencontainers.image.title="Beyvra read-only edge" \
      org.opencontainers.image.description="Read-only ingress for certified Beyvra candidates"

EXPOSE 8080

USER 101

CMD ["nginx", "-g", "daemon off;"]
