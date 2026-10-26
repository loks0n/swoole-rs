#!/bin/sh
# System packages for building and testing the hybrid. The devcontainer image and
# CI both run this, so local and CI environments cannot drift. Extra packages a job
# needs go as arguments. APT_CACHE (set by .github/actions/install) keeps the
# package files and indexes between CI runs, so most runs never touch the mirror.
set -e
[ "$(id -u)" = 0 ] || exec sudo env APT_CACHE="${APT_CACHE:-}" "$0" "$@"
export DEBIAN_FRONTEND=noninteractive
# The CI mirror sometimes throttles one connection for minutes; give up on a
# stalled download quickly and retry instead of waiting out apt's long default.
APT='-o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15 -o Acquire::Retries=5'
if [ -n "$APT_CACHE" ]; then
    mkdir -p "$APT_CACHE/archives/partial" "$APT_CACHE/lists/partial"
    APT="$APT -o Dir::Cache::Archives=$APT_CACHE/archives -o Dir::State::Lists=$APT_CACHE/lists"
fi
install() {
    apt-get $APT install -yq --no-install-recommends \
        php-dev php-sqlite3 php-curl php-xml php-mbstring python3 python3-pytest composer \
        libpcre2-dev libssl-dev zlib1g-dev pkg-config cmake g++ make autoconf git \
        ca-certificates curl libgtest-dev libnghttp2-dev libpq-dev libcurl4-openssl-dev ccache locales "$@"
}
# Cached indexes (refreshed weekly by the cache key) are enough when every package
# is cached too; if one isn't and the mirror has moved on, refresh and retry once.
if [ -n "$APT_CACHE" ] && ls "$APT_CACHE"/lists/*_Packages >/dev/null 2>&1; then
    install "$@" || { apt-get $APT update -q && install "$@"; }
else
    apt-get $APT update -q
    install "$@"
fi
[ -z "$APT_CACHE" ] || chmod -R a+rX "$APT_CACHE"
# Locales some original PHPTs switch to.
localedef -i en_US -f ISO-8859-1 en_US.ISO8859-1
localedef -i tr_TR -f ISO-8859-9 tr_TR.ISO8859-9
localedef -i tr_TR -f UTF-8 tr_TR.UTF-8
