#!/usr/bin/env python3
"""Measure prepared immutable runtimes ONLY during an acknowledged host lease."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--prepared', type=Path, required=True)
p.add_argument('--trials', type=int, default=7)
p.add_argument('--loops', type=int, default=10000)
p.add_argument('--exclusive-host-lease', required=True, help='Record actual coordinator-acknowledged measurement window; this flag does not grant permission')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
if a.trials < 1 or a.loops < 1:
    p.error('Trials and loops must be positive')
manifest = a.prepared / 'prepared.json'
prepared = json.loads(manifest.read_text())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
engines = {row['name']: row for row in prepared['engines']}
report = {'exclusive_host_lease': a.exclusive_host_lease,
          'scope': prepared['scope'], 'loops': a.loops, 'trials': a.trials, 'rows': [], 'passed_correctness': False}
try:
    for trial in range(a.trials):
        for mode in prepared['modes']:
            for name in (['upstream', 'rust'] if trial % 2 == 0 else ['rust', 'upstream']):
                engine = engines[name]
                for path, identity in [('binary', 'binary_sha256'), ('published_library', 'published_library_sha256')]:
                    if sha(engine[path]) != engine[identity]:
                        raise ValueError('Prepared identity changed: ' + engine[path])
                command = [engine['binary'], '--measure', mode, str(a.loops)]
                run = subprocess.run(command, capture_output=True, text=True, timeout=60)
                if run.returncode:
                    raise RuntimeError(str(command) + ': ' + run.stdout + run.stderr)
                row = json.loads(run.stdout)
                if row['checksum'] != a.loops or row['count'] != a.loops or row['nanoseconds'] < 1:
                    raise ValueError('Measured correctness witness differs')
                report['rows'].append({'trial': trial, 'engine': name, **row})
                a.output.parent.mkdir(parents=True, exist_ok=True)
                a.output.write_text(json.dumps(report, indent=2) + '\n')
    for engine in engines.values():
        if sha(engine['binary']) != engine['binary_sha256'] or sha(engine['published_library']) != engine['published_library_sha256']:
            raise ValueError('Prepared identity changed during measurements')
    report['summary'] = []
    for mode in prepared['modes']:
        medians = {name: statistics.median(row['nanoseconds'] for row in report['rows'] if row['engine'] == name and row['mode'] == mode) for name in engines}
        report['summary'].append({'mode': mode, 'median_nanoseconds': medians,
                                  'rust_throughput_ratio': medians['upstream'] / medians['rust']})
    report['passed_correctness'] = True
except Exception as error:
    report['error'] = str(error)
finally:
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(not report['passed_correctness'])
