#!/bin/sh
# System packages for building and testing the hybrid. The devcontainer image and
# the merge tier both run this, so local and CI environments cannot drift.
set -e
[ "$(id -u)" = 0 ] || exec sudo "$0" "$@"
export DEBIAN_FRONTEND=noninteractive
# The CI mirror sometimes throttles one connection for minutes; give up on a
# stalled download quickly and retry instead of waiting out apt's long default.
APT='-o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15 -o Acquire::Retries=5'
apt-get $APT update -q
apt-get $APT install -yq --no-install-recommends \
    php-dev php-sqlite3 php-curl php-xml php-mbstring python3 python3-pytest composer \
    libpcre2-dev libssl-dev zlib1g-dev pkg-config cmake g++ make autoconf git \
    ca-certificates curl libgtest-dev libnghttp2-dev libpq-dev libcurl4-openssl-dev ccache locales
# Locales some original PHPTs switch to.
localedef -i en_US -f ISO-8859-1 en_US.ISO8859-1
localedef -i tr_TR -f ISO-8859-9 tr_TR.ISO8859-9
localedef -i tr_TR -f UTF-8 tr_TR.UTF-8
