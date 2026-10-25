#!/usr/bin/env python3
"""Validate prepared actual native consumers; --measure requires an exclusive host lease."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(prepared):
    if {e['engine'] for e in prepared['engines']} != {'upstream', 'reactor'} or len(prepared['engines']) != 2:
        raise ValueError('Exactly one upstream and one reactor consumer required')
    for engine in prepared['engines']:
        symbols = subprocess.check_output(['nm', '-gU' if sys.platform == 'darwin' else '-D', engine['library']],text=True)
        exports = {line.split()[-1].lstrip('_') for line in symbols.splitlines() if 'swr_v1_reactor_' in line or 'swr_v1_stream_' in line}
        expected = {'swr_v1_reactor_ready','swr_v1_reactor_interest','swr_v1_reactor_filter','swr_v1_reactor_write','swr_v1_stream_prepare','swr_v1_stream_length','swr_v1_stream_view'} if engine['engine'] == 'reactor' else set()
        if exports != expected:
            raise ValueError('Unexpected actual Rust library exports: '+str(exports))
        for kind in ['binary', 'library']:
            if sha(engine[kind]) != engine[kind+'_sha256']:
                raise ValueError('Prepared artifact changed: '+engine[kind])
    if len({e['binary_sha256'] for e in prepared['engines']}) != 2 or len({e['library_sha256'] for e in prepared['engines']}) != 2:
        raise ValueError('Consumers and libraries must be distinct')
    if next(e for e in prepared['engines'] if e['engine'] == 'upstream')['archive_sha256'] is not None:
        raise ValueError('Control unexpectedly declares Rust archive')
    if not next(e for e in prepared['engines'] if e['engine'] == 'reactor')['archive_sha256']:
        raise ValueError('Candidate lacks exact Rust archive provenance')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--backend', action='append', choices=['poll','kqueue','epoll'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--measure', action='store_true', help='Execute optimized timing only inside an integrator-granted exclusive lease')
    args = parser.parse_args()
    prepared_bytes = args.prepared.read_bytes();prepared = json.loads(prepared_bytes)
    source = Path(__file__).with_suffix('.cc')
    if sha(source) != prepared['source_sha256']:
        raise ValueError('Prepared consumer does not match current source')
    validate(prepared)
    if not args.measure:
        print('Prepared binary/library/source hashes verified; no workload executed')
        return 0
    started = time.monotonic()
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), scope=__doc__, prepared=prepared,
                  pairs=[], passed=False, limits='Local optimized microbenchmarks; no overall application throughput or activation claim. Interest is the existing inline no-op path; ready leaves one datagram readable. No TLS, queued writes or idle waits timed.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    engines = {e['engine']:e for e in prepared['engines']}
    workloads = [(backend, workload) for backend in args.backend for workload in ['ready','interest','write']]
    try:
        for trial in range(6):
            cases = workloads[trial % len(workloads):]+workloads[:trial % len(workloads)]
            if trial % 2: cases.reverse()
            for index,(backend,workload) in enumerate(cases):
                iterations = 5000000 if workload == 'interest' else 100000
                pair = dict(trial=trial, backend=backend, workload=workload, rows=[])
                report['pairs'].append(pair)
                order = ['upstream','reactor'] if (trial+index)%2 == 0 else ['reactor','upstream']
                for name in order:
                    command = [engines[name]['binary'],workload,backend,str(iterations)]
                    result = subprocess.run(command,capture_output=True,text=True,timeout=5)
                    row = dict(engine=name,command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr)
                    pair['rows'].append(row)
                    data = json.loads(result.stdout)
                    if result.returncode or result.stderr or data['errors'] or data['workload'] != workload or data['backend'] != backend or data['iterations'] != iterations or data['elapsed_ns'] <= 0:
                        raise ValueError('Consumer correctness failed: '+str(row))
                    row['result'] = data
                values = {r['engine']:r['result'] for r in pair['rows']}
                if values['upstream']['checksum'] != values['reactor']['checksum']:
                    raise ValueError('Matched consumers disagree on result')
                pair['reactor_over_upstream'] = values['reactor']['elapsed_ns']/values['upstream']['elapsed_ns']
        validate(prepared)
        if args.prepared.read_bytes() != prepared_bytes or sha(source) != prepared['source_sha256']:
            raise ValueError('Prepared source changed during measurement')
        report['ratios'] = {backend+'/'+workload:statistics.median(p['reactor_over_upstream'] for p in report['pairs'] if p['backend']==backend and p['workload']==workload) for backend,workload in workloads}
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    finally:
        report['wall_seconds'] = time.monotonic()-started
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','wall_seconds','ratios','error'] if k in report}))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
