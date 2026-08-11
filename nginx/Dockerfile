FROM nginx:1.29-alpine

ARG CONFIG_FILE=nginx.prod.conf.template

WORKDIR /app

RUN apk upgrade --no-cache

RUN rm /etc/nginx/conf.d/default.conf

COPY ./nginx.conf /etc/nginx/nginx.conf

COPY ./nginx.conf /etc/nginx/default.conf

RUN mkdir /etc/nginx/templates

COPY $CONFIG_FILE /etc/nginx/templates

RUN chown -R nginx:nginx /etc/nginx/conf.d /etc/nginx/templates /var/cache/nginx && \
    chmod -R u=rwX,g=rX,o= /etc/nginx/conf.d /etc/nginx/templates /var/cache/nginx

EXPOSE 80

USER nginx

CMD ["nginx", "-g", "daemon off;"]
