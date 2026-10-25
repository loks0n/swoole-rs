#!/usr/bin/env python3
"""Diagnostic only: two initialized reference pointers, never pristine-baseline parity."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import overlay

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated, write_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--core-root', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--openssl-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    overlay.SOURCE = args.source
    report = {'scope': __doc__, 'upstream_pin': overlay.PIN, 'platform': sys.platform,
              'passed': False, 'pristine_original_passed': False, 'results': []}
    try:
        tree = args.core_root.resolve() / 'core-upstream'
        folder = args.output.resolve().with_suffix('')
        folder.mkdir(parents=True, exist_ok=True)
        original = overlay.original('src/wrapper/http.cc')
        corrected = original.replace('multipart_parser *mt_parser;', 'multipart_parser *mt_parser = nullptr;').replace('String *form_data_buffer;', 'String *form_data_buffer = nullptr;')
        if corrected == original:
            raise ValueError('Reference initializers no longer match')
        source = folder / 'initialized-http.cc'
        source.write_text(corrected)
        binary = folder / 'initialized-witness'
        library = (tree / ('lib/libswoole.dylib' if sys.platform == 'darwin' else 'lib/libswoole.so')).resolve()
        command = ['c++', '-std=c++14', '-O2', '-UNDEBUG', '-DHAVE_CONFIG_H',
                   '-I' + str(tree), '-I' + str(tree / 'include'), '-I' + str(tree / 'thirdparty/llhttp'),
                   str(Path(__file__).with_name('native.cc')), str(source), '-L' + str(tree / 'lib'),
                   '-Wl,-rpath,' + str(tree / 'lib'), '-lswoole', '-lpthread', '-o', str(binary)]
        if args.openssl_root:
            command[1:1] = ['-I' + str(args.openssl_root / 'include'), '-L' + str(args.openssl_root / 'lib')]
        if sys.platform == 'linux': command.append('-ldl')
        result = run_isolated(command, timeout=90)
        report.update(compile=command, compile_exit=result.returncode, compile_stderr=result.stderr,
                      expected_core_library=str(library), core_library_sha256=sha(library))
        if result.returncode:
            raise RuntimeError('Diagnostic compile failed')
        report['corrected_binary_sha256'] = sha(binary)
        baseline = json.loads(args.observations.read_text())
        for scenario in ['get', 'empty-query', 'form', 'multipart', 'file']:
            result = run_isolated([str(binary), scenario], timeout=30)
            row = {'scenario': scenario, 'exit': result.returncode, 'stdout': result.stdout,
                   'stderr': result.stderr, 'status': 'failed'}
            report['results'].append(row)
            images = {line.split('=', 1)[0]: str(Path(line.split('=', 1)[1]).resolve())
                      for line in result.stderr.splitlines() if line.startswith(('SWR_WRAPPER_LIBRARY=', 'SWR_CORE_LIBRARY='))}
            row['loaded_images'] = images
            row['loaded_images_verified'] = images.get('SWR_WRAPPER_LIBRARY') == str(binary) and \
                images.get('SWR_CORE_LIBRARY') == str(library) and sha(binary) == report['corrected_binary_sha256'] and sha(library) == report['core_library_sha256']
            if result.returncode == 0:
                row['observations'] = json.loads(result.stdout.strip().splitlines()[-1])
                expected = next(x['observations'] for x in baseline['results'] if x['engine'] == 'rust' and x['scenario'] == scenario)
                row['matches_rust'] = row['observations'] == expected
                row['status'] = 'passed' if row['matches_rust'] and row['loaded_images_verified'] else 'failed'
        report['passed'] = all(row['status'] == 'passed' for row in report['results'])
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'error': report.get('error')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
