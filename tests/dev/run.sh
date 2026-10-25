#!/bin/sh
# Run each tooling test file in its own process, in parallel. Most tests wait on
# compilers, git or ccache subprocesses, so files overlap well.
cd "$(dirname "$0")/../.." || exit 1
logs=$(mktemp -d)
pids=
for test in tests/dev/test_*.py; do
    name=${test##*/}
    python3 -m unittest discover -s tests/dev -p "$name" -q > "$logs/$name.log" 2>&1 &
    pids="$pids $!:$name"
done
status=0
for entry in $pids; do
    if ! wait "${entry%%:*}"; then
        status=1
        echo "FAILED ${entry#*:}"
        cat "$logs/${entry#*:}.log"
    fi
done
rm -rf "$logs"
exit $status
