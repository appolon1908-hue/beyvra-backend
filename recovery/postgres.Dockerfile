FROM postgres:16-alpine

# The verifier always runs as postgres and stores disposable data under /tmp.
# Removing the unused root-to-postgres helper also removes its vulnerable static
# Go runtime from the recovery image; the official entrypoint supports non-root.
USER root
RUN rm -f /usr/local/bin/gosu
ENV PGDATA=/tmp/pgdata
USER postgres

