# BASE_IMAGE is the current dev image (see tests/modules/protocols/README.md). The default
# names the missing build argument instead of pinning a tag that goes stale.
ARG BASE_IMAGE=pass-build-arg-base-image
FROM ${BASE_IMAGE}
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends cmake libgtest-dev libnghttp2-dev libpq-dev redis-server && rm -rf /var/lib/apt/lists/*
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
