#!/usr/bin/env python3
"""Source-bound original and exact-wire trailer runtime for the selected lowercase implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import parse_engines, run_isolated, write_report
from tools.hybrid_identity import attest
from lowercase_wire import run_wire


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = dict(passed=False, scope=__doc__, runtime_launched=False)
    selection = Path(__file__).with_name('lowercase-originals.json')
    try:
        source = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', args.source_ref + '^{commit}'], text=True).strip()
        contents = subprocess.check_output(['git', '-C', str(ROOT), 'show', source + ':crates/utilities/src/bytes.rs'])
        if b'fn swr_v1_utils_lowercase(' not in contents:
            raise ValueError('Selected source predates the complete lowercase export; no runtime launched')
        engines = parse_engines(args.engine, args.php, args.php_extension)
        identities = [engine.metadata() for engine in engines]
        report['engines'] = identities
        if {bool(row['rust_feature_bits'] & 512) for row in identities} != {False, True}:
            raise ValueError('Require native and selected utilities engines')
        selected = next(row for row in identities if row['rust_feature_bits'] & 512)
        report['source_attestation'] = attest(args.build_manifest, args.archive, selected, source, 512)
        symbols = run_isolated(['nm', *(['-D'] if sys.platform.startswith('linux') else []), '-g', selected['extension']], timeout=30)
        report['selected_symbols'] = dict(exit=symbols.returncode, stdout=symbols.stdout, stderr=symbols.stderr)
        import re
        if symbols.returncode or not re.search(r'\b[TW]\s+_?swr_v1_utils_lowercase$', symbols.stdout, re.M):
            raise ValueError('Actual selected DSO lacks a defined lowercase export')
        output = args.output.resolve()
        original_report = output.with_name(output.stem + '-originals.json')
        command = [sys.executable, str(ROOT / 'corpus/upstream/run.py'), '--source', str(args.source),
                   '--php', args.php, '--manifest', str(selection), '--require-all', '--output', str(original_report)]
        for extension in args.php_extension:
            command += ['--php-extension', extension]
        for value in args.engine:
            command += ['--engine', value]
        report['runtime_launched'] = True
        result = run_isolated(command, timeout=90)
        report['original_command'] = dict(argv=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
        if original_report.is_file():
            report['original_report'] = str(original_report)
            original = json.loads(original_report.read_text())
            report['outcomes'] = original['results']
        else:
            raise ValueError('Official original runner produced no report')
        if result.returncode or len(original['results']) != len(engines) or any(row['status'] != 'passed' for row in original['results']):
            raise ValueError('Original trailer gate did not pass; first outcomes preserved')
        wire_output = output.with_name(output.stem + '-wire.json')
        wire = run_wire(args.source, engines, wire_output)
        report['wire_report'] = str(wire_output)
        if not wire['passed']:
            raise ValueError('Exact-wire trailer fixture did not pass; engine outputs preserved')
        if any(sha(row['extension']) != row['sha256'] for row in identities):
            raise ValueError('Engine changed during original execution')
        receipt = report['source_attestation']
        if sha(args.build_manifest) != receipt['manifest_sha256'] or sha(args.archive) != receipt['archive_sha256']:
            raise ValueError('Selected receipt/archive changed during original execution')
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    write_report(args.output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'runtime_launched']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
