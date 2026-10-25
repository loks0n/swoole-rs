#!/usr/bin/env python3
"""Explicit supplemental versioned-expectation profile; untouched original gates stay separate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from corpus.upstream.run import COMMIT, prepare, record_result, run_cases, save_report
from tools.harness import parse_engines
from tools.phpt_expectations import select
import subprocess

RULES_SHA = '06375dd3b2038c81a7df149ee181206c165734dc0e7aaa2ddcb6c49c47f58462'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--case', action='append', required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sha = lambda value: hashlib.sha256(value).hexdigest()
    report = {'passed': False, 'scope': __doc__, 'upstream_commit': COMMIT, 'runner_sha256': sha(Path(__file__).read_bytes()),
              'adapter_sha256': sha(Path(__file__).parents[2].joinpath('tools/phpt_expectations.py').read_bytes()),
              'untouched_original_gate_passed': False, 'whole_inventory_passed': False,
              'engines': [], 'results': [], 'batches': [], 'adaptations': [], 'execution_status': 'running'}
    save_report(args.output, report)
    try:
        rules = subprocess.check_output(['git', '-C', str(args.source), 'show', COMMIT + ':tests/run-tests'])
        if sha(rules) != RULES_SHA:
            raise ValueError('Pinned upstream expectation selection rules differ')
        report['upstream_rules_sha256'] = RULES_SHA
        cases = []
        for path in dict.fromkeys(args.case):
            if not path.startswith('tests/') or not path.endswith('.phpt') or '..' in Path(path).parts:
                raise ValueError('Require a pinned original PHPT path')
            data = subprocess.check_output(['git', '-C', str(args.source), 'show', COMMIT + ':' + path])
            cases.append({'path': path, 'sha256': sha(data), 'module': 'explicit-versioned-expectation', 'requires': ['upstream_test_bootstrap']})
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            metadata = engine.metadata()
            report['engines'].append(metadata)
            missing = {'upstream_test_bootstrap'} - set(metadata['capabilities'])
            if missing:
                for case in cases:
                    record_result(report, engine, case, {'status': 'unsupported', 'detail': 'missing capabilities: ' + ', '.join(sorted(missing))})
                continue
            version = subprocess.check_output(engine.command('-r', 'echo PHP_VERSION_ID;'), text=True)
            version = int(version)
            with tempfile.TemporaryDirectory(prefix='swr-phpt-versioned-') as temporary:
                sandbox = Path(temporary)
                prepare(args.source, sandbox, cases)
                (sandbox / 'home').mkdir(); (sandbox / 'tmp').mkdir()
                for index, case in enumerate(cases):
                    path = sandbox / case['path']; original = path.read_bytes()
                    adapted, receipt = select(original, version)
                    if not receipt['conditional_sections']:
                        raise ValueError('No conditional original expectation in ' + case['path'])
                    artifact = args.output.resolve().with_name(args.output.stem + '-artifacts') / engine.name / str(index)
                    artifact.mkdir(parents=True)
                    (artifact / 'original.phpt').write_bytes(original)
                    (artifact / 'adapted.phpt').write_bytes(adapted)
                    path.write_bytes(adapted)
                    ini = ['fatal_error_backtraces=On'] if version >= 80500 else []
                    rows, timing = run_cases(engine, [case], sandbox, artifact, 90, 1, runner_ini=ini)
                    receipt.update(engine=engine.name, test=case['path'], official_runner_ini=ini,
                                   official_runner_sha256=sha((sandbox / 'run-tests.php').read_bytes()))
                    report['adaptations'].append(receipt)
                    record_result(report, engine, case, {**rows[case['path']], 'expectation_adapter': receipt})
                    report['batches'].append({'engine': engine.name, **timing})
                    save_report(args.output, report)
        report['execution_status'] = 'complete'
        report['passed'] = bool(report['results']) and all(row['status'] == 'passed' for row in report['results'])
    except Exception as error:
        report.update(execution_status='failed', error=str(error))
    finally:
        if report['execution_status'] == 'running':
            report['execution_status'] = 'interrupted'
        save_report(args.output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'execution_status', 'error']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
