# Build the repository's dev image first; override BASE_IMAGE for its current tag.
ARG BASE_IMAGE=swoole-rs-dev:9af42f7b95c33bf3
FROM ${BASE_IMAGE}
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends cmake libgtest-dev libnghttp2-dev libpq-dev redis-server && rm -rf /var/lib/apt/lists/*
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
