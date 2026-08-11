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

RUN chgrp -R 0 /etc/nginx/conf.d && \
    chmod -R g=u /etc/nginx/conf.d

EXPOSE 8080

USER 101

CMD ["nginx", "-g", "daemon off;"]
