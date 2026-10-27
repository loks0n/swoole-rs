#!/usr/bin/env bash
# Re-run the PHPT gate's flagged tests up to three times per engine, upstream first. Upstream
# stops at a test's first failed re-run; the hybrid then re-runs every flagged test until its
# verdict is settled, once only when its first failure timed out (gate.py --print-pending).
#   recheck.sh RESULTS_DIR ENGINES_DIR RECHECK_DIR [run.py arguments...]
# ENGINES_DIR holds upstream.so and hybrid.so; RECHECK_DIR receives <engine>-<attempt>.json.
set -eo pipefail
results=$1 engines=$2 recheck=$3
shift 3
mkdir -p "$recheck"
pending() {
  local engine=$1
  set -- "$results"/*.json
  if ls "$recheck"/*.json >/dev/null 2>&1; then set -- "$@" --recheck "$recheck"/*.json; fi
  # It prints an empty line when nothing is pending; that must not become a bare --case.
  python3 corpus/upstream/gate.py "$@" --print-pending "$engine" | sed -n 's/^\(..*\)$/--case \1/p' | tr '\n' ' '
}
for engine in upstream hybrid; do
  for attempt in 1 2 3; do
    cases=$(pending "$engine")
    [ -n "$cases" ] || break
    # shellcheck disable=SC2086 # one --case per word
    python3 corpus/upstream/run.py "$@" $cases --engine "$engine=$engines/$engine.so" \
      --output "$recheck/$engine-$attempt.json" || [ $? -eq 1 ]
  done
done
