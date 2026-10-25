#!/usr/bin/env python3
"""Three unchanged collection class-handler originals outside Table/Channel groups."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from gate import ROOT, PIN, sha
from corpus.upstream.tree import inventory
from tools.build_upstream import require_build_space
from tools.harness import write_report

CASES = tuple('tests/swoole_global/' + name + '.phpt' for name in
              ['channel_construct_check', 'unset_deny', 'unset_property_01'])


def manifest(source):
    complete = inventory(source, 'swoole_global', 'phpcollections', ['upstream_test_bootstrap', 'coroutines'])
    selected = {row['path']: row for row in complete['tests'] if row['path'] in CASES}
    if len(selected) != len(CASES):
        raise ValueError('Collection handler original missing from pinned inventory')
    complete['tests'] = [selected[path] for path in CASES]
    complete['inventory'].update(cases=3, selection='Exact three collection-only class-handler originals; not full swoole_global coverage')
    return complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    work = output.parent / ('phpcollections-handlers-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, pin=PIN,
                  source_ref=args.source_ref, commands=[],
                  baseline_replaced=False, work=str(work), performance_measured=False)

    def run(command):
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        report['commands'].append(dict(command=list(map(str, command)), exit=result.returncode,
                                       stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        return result

    try:
        require_build_space(ROOT)
        require_build_space(work)
        manifest_path = work / 'handler-originals.json'
        write_report(manifest_path, manifest(args.source))
        report['inventory'] = dict(path=str(manifest_path), cases=list(CASES))
        flags = [flag for name in args.php_extension for flag in ['--php-extension', name]]
        engines = [flag for engine in args.engine for flag in ['--engine', engine]]
        runtime_path = work / 'runtime.json'
        command = [sys.executable, ROOT / 'tests/modules/phpcollections/php_runtime.py',
                   '--php', args.php, *flags, *engines, '--build-manifest', args.build_manifest,
                   '--archive', args.archive, '--source-ref', args.source_ref, '--output', runtime_path]
        if run(command).returncode:
            raise ValueError('Current source-attested runtime prerequisite failed')
        runtime = json.loads(runtime_path.read_text())
        report['runtime'] = runtime
        if not runtime['passed'] or len(runtime['engines']) != 2:
            raise ValueError('Source-attested actual engine pair required')
        copied = [flag for engine in runtime['engines'] for flag in ['--engine', engine['name'] + '=' + engine['extension']]]
        original_path = work / 'originals.json'
        result = run([sys.executable, ROOT / 'corpus/upstream/run.py', '--source', args.source,
                      '--manifest', manifest_path, '--php', args.php, *flags, *copied,
                      '--require-all', '--isolate-cases', '--timeout', '90', '--output', original_path])
        if original_path.is_file():
            report['originals'] = json.loads(original_path.read_text())
        if result.returncode:
            raise ValueError('Original handler failure/skip/unsupported retained')
        if any(sha(row['extension']) != row['sha256'] for row in runtime['engines']):
            raise ValueError('Copied extension changed')
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
