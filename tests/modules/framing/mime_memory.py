#!/usr/bin/env python3
"""Clock-free original/M18 MIME lookup allocation-failure comparison."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import overlay

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allocation-ceiling', type=int, default=128, help='Per-C++allocation byte ceiling; 0 is uncapped control')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--configured-root', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--openssl-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.allocation_ceiling < 0: parser.error('Allocation ceiling must be nonnegative')
    overlay.SOURCE = args.source
    tree = args.configured_root.resolve()
    report = {'scope': __doc__, 'allocation_ceiling': args.allocation_ceiling, 'platform': sys.platform, 'upstream_pin': overlay.PIN,
              'results': [], 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-mime-memory-') as temporary:
        directory = Path(temporary)
        for engine in ['upstream', 'rust']:
            source = directory / (engine + '.cc')
            source.write_text(overlay.original('src/protocol/mime_type.cc') if engine == 'upstream' else overlay.generated()['src/protocol/mime_type.cc'])
            binary = directory / engine
            command = ['c++', '-std=c++14', '-O2', '-UNDEBUG', '-DHAVE_CONFIG_H', '-DSWOOLE_RS_FRAMING',
                       '-I' + str(tree), '-I' + str(tree / 'include'), '-I' + str(ROOT / 'native/framing'),
                       str(Path(__file__).with_suffix('.cc')), str(source), '-o', str(binary)]
            if args.openssl_root: command[1:1] = ['-I' + str(args.openssl_root / 'include')]
            if engine == 'rust': command += [str(args.archive.resolve()), '-lpthread', '-lm']
            if sys.platform == 'linux': command.append('-ldl')
            result = run_isolated(command, timeout=90)
            row = {'engine': engine, 'compile': command,
                   'compile_exit': result.returncode, 'compile_stderr': result.stderr, 'passed': False}
            report['results'].append(row)
            if result.returncode: continue
            result = run_isolated([str(binary), str(args.allocation_ceiling)], timeout=30)
            row.update(exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
            row['cases'] = [json.loads(line) for line in result.stdout.splitlines()]
            row['passed'] = result.returncode == 0 and len(row['cases']) == 3 and all(
                case['value_matches'] and not case['bad_alloc'] for case in row['cases'])
    report['passed'] = len(report['results']) == 2 and all(row['passed'] for row in report['results'])
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'engines': [{key: row.get(key) for key in ['engine', 'passed', 'cases']} for row in report['results']]}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
