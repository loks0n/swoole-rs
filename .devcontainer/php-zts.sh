#!/bin/sh
# A thread-safe (ZTS) PHP 8.3 in $1 (default target/php-zts), for --enable-swoole-thread
# builds and the swoole_thread PHPTs (.github/workflows/zts.yml). Ubuntu ships only
# NTS PHP, so build the release from source with the extensions those tests call
# (sockets, pcntl, posix, curl, openssl) compiled in; install.sh has the libraries.
# Does nothing when the prefix already holds this release (CI caches it).
set -e
VERSION=8.3.36
SHA256=c93f3441f87f6ab156bef4432db215d7e61ca2c0183bb3a2aa28d9886ab59f53
PREFIX=$(realpath -m "${1:-target/php-zts}")
if [ "$("$PREFIX/bin/php" -r 'echo PHP_VERSION, PHP_ZTS;' 2>/dev/null)" = "${VERSION}1" ]; then
    exit 0
fi
src=$(mktemp -d)
curl -fsSL --retry 5 -o "$src/php.tar.gz" "https://www.php.net/distributions/php-$VERSION.tar.gz"
echo "$SHA256  $src/php.tar.gz" | sha256sum -c -
tar -xzf "$src/php.tar.gz" -C "$src" --strip-components=1
(cd "$src" && ./configure --prefix="$PREFIX" --enable-zts --disable-cgi --disable-phpdbg \
    --without-libxml --disable-dom --disable-simplexml --disable-xml --disable-xmlreader --disable-xmlwriter \
    --without-sqlite3 --without-pdo-sqlite --enable-sockets --enable-pcntl --enable-mbstring --disable-mbregex \
    --with-curl --with-openssl --with-zlib >/dev/null && make -j"$(nproc)" >/dev/null && make install >/dev/null)
rm -rf "$src"
"$PREFIX/bin/php" -v
