#!/bin/sh
# Regenerate native/include/swoole_rs_<crate>.h for every crate with a cbindgen.toml.
# --check leaves files alone and fails, with a diff, if any committed header is stale.
set -e
cd "$(dirname "$0")/.."
status=0
for config in crates/*/cbindgen.toml; do
    crate=$(dirname "$config")
    header=native/include/swoole_rs_$(basename "$crate").h
    generated=$(mktemp)
    cbindgen --quiet --config "$config" --output "$generated" "$crate"
    if [ "$1" = --check ]; then
        if ! cmp -s "$generated" "$header"; then
            echo "$header is stale; run tools/headers.sh" >&2
            diff -u "$header" "$generated" >&2 || true
            status=1
        fi
        rm -f "$generated"
    else
        mv "$generated" "$header"
    fi
done
exit $status
