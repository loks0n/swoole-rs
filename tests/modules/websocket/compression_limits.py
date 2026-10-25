#!/usr/bin/env python3
"""Compare deliberate native WebSocket allocation failures in real PHP children."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, parse_engines, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', default=str(ROOT / 'target/reports/websocket-compression-limits.json'))
    args = parser.parse_args()
    engines = parse_engines(args.engine, args.php, args.php_extension)
    if len(engines) != 2:
        parser.error('Provide exactly two engines')
    entry = Path(__file__).with_suffix('.php')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Requested 8MiB PHP memory-limit failures; exact per-platform output parity, not allocator-phase attribution or Rust sanitizer coverage',
              'engines': [engine.metadata() for engine in engines],
              'results': [], 'differences': []}
    for mode in ['deflate-success', 'deflate-fatal', 'inflate']:
        outcomes = []
        outputs = []
        for engine in engines:
            result = run_isolated(engine.command(entry, mode), timeout=15)
            output = result.stdout + result.stderr
            marker = 'BEGIN_INFLATE' if mode == 'inflate' else 'BEGIN_DEFLATE'
            memory_fatal = bool(re.search(r'(Allowed memory size|Hard memory limit).*exhausted', output))
            returned = 'RETURNED' in output
            valid = (marker in output and ((result.returncode == 0 and returned and not memory_fatal)
                     if mode == 'deflate-success' else
                     (result.returncode != 0 and memory_fatal and not returned)))
            # Compare complete first outputs within one PHP/platform, including
            # fatal allocation size, source line and exit status.
            outcome = {'began': marker in output, 'returned': returned,
                       'memory_fatal': memory_fatal, 'exit_code': result.returncode}
            outcomes.append(outcome)
            outputs.append((result.stdout, result.stderr))
            report['results'].append({'engine': engine.name, 'mode': mode, 'valid': valid,
                                      'outcome': outcome, 'stdout': result.stdout, 'stderr': result.stderr})
        if outcomes[0] != outcomes[1] or outputs[0] != outputs[1]:
            report['differences'].append(mode)
    report['passed'] = all(row['valid'] for row in report['results']) and not report['differences']
    write_report(args.output, report)
    print(f"6 subprocess outcomes; passed={report['passed']}; {args.output}")
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
