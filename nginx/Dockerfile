FROM nginxinc/nginx-unprivileged:1.29-alpine

USER root

ARG CONFIG_FILE=nginx.prod.conf.template

WORKDIR /app

RUN apk upgrade --no-cache

RUN rm /etc/nginx/conf.d/default.conf

COPY ./nginx.conf /etc/nginx/nginx.conf

COPY ./nginx.conf /etc/nginx/default.conf

RUN mkdir /etc/nginx/templates

COPY $CONFIG_FILE /etc/nginx/templates

RUN chown -R nginx:nginx /etc/nginx/conf.d /etc/nginx/templates && \
    chmod -R u=rwX,go=rX /etc/nginx/conf.d /etc/nginx/templates

EXPOSE 8080

USER 101

USER nginx

CMD ["nginx", "-g", "daemon off;"]
