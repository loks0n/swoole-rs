#!/usr/bin/env python3
"""Instrument actual native thread-context baton ownership; no support claim."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT))
from tools.build_upstream import COMMIT as PIN
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
source = subprocess.check_output(['git', '-C', str(a.source), 'show', PIN + ':src/coroutine/thread_context.cc'], text=True)
# Keep all actual policy function bodies. Only the mutex type is replaced;
# supporting Timer/Reactor/signal acquisition is explicitly a native facade.
body = '#ifdef SW_USE_THREAD_CONTEXT\n' + source[source.index('namespace swoole {'):].replace('std::mutex', 'CheckedMutex')
with tempfile.TemporaryDirectory(prefix='swr-thread-context-audit-') as tmp:
    tree = Path(tmp)
    (tree / 'actual-thread-context.inc').write_text(body)
    binary = tree / 'audit'
    command = ['c++', '-std=c++14', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
               '-I' + str(tree), str(ROOT / 'tests/modules/coroutine/thread_context_audit.cc'), '-pthread', '-o', str(binary)]
    build = subprocess.run(command, capture_output=True, text=True)
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10) if build.returncode == 0 else build
    report = dict(upstream_commit=PIN,
                  scope='Actual pinned native baton bodies; std::mutex replaced with error-checking diagnostic mutex; timer/global/signal native facades. Errors recorded without throwing, so post-error continuation is diagnostic, not equivalent execution.',
                  optional_thread_context_supported=False, rust_instrumentation=False,
                  diagnostic_status='expected_ownership_violations_observed' if run.returncode == 0 else 'diagnostic_failed',
                  command=command, compile_returncode=build.returncode, compile_stderr=build.stderr,
                  returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(run.stdout, end='')
    print(run.stderr, end='')
    raise SystemExit(run.returncode)
