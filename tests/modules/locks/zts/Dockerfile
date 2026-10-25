# Frozen official PHP ZTS runtime; scoped synchronization validation only.
FROM php:8.5-zts-bookworm@sha256:be3a5190f1d9c4c1956619b263ce471b7987487038f03fdbddcfc0b99647916c
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 git g++ make autoconf pkg-config libssl-dev libpcre2-dev \
    && rm -rf /var/lib/apt/lists/*
RUN docker-php-ext-install sockets
WORKDIR /work
