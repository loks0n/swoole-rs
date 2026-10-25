#!/usr/bin/env python3
"""Execute complete primary M07 originals from attested frozen native-core artifacts.

Existing common builder receipts identify unchanged assertions, exact executable,
archive, config, patch and loaded native library. This runner supplies the original
base.file_put_contents fixture before independent hook/socket/system test processes.
Optional io_uring and dependency inventories remain explicit unexecuted gates.
"""
import argparse
from datetime import datetime, timezone
import fnmatch
import json
import subprocess
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import run_isolated, write_report
from tools.native_core import library_identity, sha, test_outcome, verify_loader

ROOT = Path(__file__).resolve().parents[3]
from tools.build_upstream import COMMIT as PIN
GROUPS = ['coroutine_hook.*', 'coroutine_socket.*', 'coroutine_system.*']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt', action='append', required=True, help='NAME=immutable native_core.py receipt')
    p.add_argument('--case', action='append', default=[], help='Explicit primary subset; all remaining primary cases stay unmeasured')
    p.add_argument('--timeout', type=int, default=35)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.timeout < 1:
        p.error('--timeout must be positive')
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), scope=__doc__, source_pin=PIN,
                  engines=[], results=[], passed=False, execution_status='running',
                  optional_io_uring='Explicitly excluded units remain UNSUPPORTED; other optional units are NOT_RUN by this primary gate',
                  extended_dependency_inventory='Only100 primary declarations plus incidental accept original execute; remaining extended dependencies NOT_RUN')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    artifacts = a.output.resolve().with_name(a.output.stem+'-artifacts')
    try:
        native = json.loads((ROOT/'tests/modules/hooks/originals.json').read_text())['native_tests']
        expected = {row['path']: row['sha256'] for row in native if row['scope'] == 'primary'}
        declared = {case['suite']+'.'+case['name'] for row in native if row['scope']=='primary' for case in row['declarations']}
        artifacts.mkdir(parents=True)
        for entry in a.receipt:
            name, sep, value = entry.partition('=')
            if not sep or not name or not value or name in [e['name'] for e in report['engines']]:
                raise ValueError('Unique NAME=receipt required')
            source = Path(value).resolve(strict=True)
            previous = json.loads(source.read_text())
            if previous['source_commit'] != PIN or previous['status'] != 'complete':
                raise ValueError('Incomplete or foreign native source receipt')
            if any(previous['original_assertion_files'].get(path) != digest for path, digest in expected.items()):
                raise ValueError('Original primary assertion identities differ')
            executable = Path(previous['execution_binary'])
            if sha(executable) != previous['execution_binary_sha256']:
                raise ValueError('Execution binary changed')
            library = previous['native_library']
            if library_identity(library['path']) != library:
                raise ValueError('Native library changed')
            engine_artifacts = artifacts/name
            engine_artifacts.mkdir(parents=True)
            tree = executable.parent.parent
            loader = verify_loader(executable, tree, library, engine_artifacts/'loader.log')
            inventory = [case for case in previous['inventory'] if any(fnmatch.fnmatchcase(case, group) for group in GROUPS)]
            if 'base.file_put_contents' not in previous['inventory']:
                raise ValueError('Original fixture assertion absent')
            if not inventory:
                raise ValueError('No configured primary originals')
            if set(a.case)-set(inventory):
                raise ValueError('Unknown exact primary --case')
            selected = a.case or inventory
            record = dict(name=name, input_receipt=str(source), identity=previous['identity'],
                          executable=str(executable), native_library=library,
                          loader_probe=loader, inventory=inventory, unmeasured=[case for case in inventory if case not in selected],
                          input_build_receipt=previous['build_receipt_sha256'], inputs=previous['inputs'], excluded_units=previous['excluded_units'], unsupported_primary=sorted(declared-set(inventory)))
            report['engines'].append(record)
            # The original full suite's base tests establish TEST_TMP_FILE.
            # Run its unchanged assertion body instead of inventing fixture bytes.
            setup_xml = engine_artifacts/'fixture.xml'
            setup = run_isolated([str(executable), '--gtest_filter=base.file_put_contents', '--gtest_output=xml:'+str(setup_xml)], cwd=tree, timeout=a.timeout)
            setup_log = engine_artifacts/'fixture.log'
            setup_log.write_text(setup.stdout+setup.stderr)
            record['fixture'] = dict(test='base.file_put_contents', exit=setup.returncode, log=str(setup_log), **test_outcome(setup_xml, 'base.file_put_contents', setup.returncode))
            if record['fixture']['status'] != 'passed':
                raise ValueError('Original native fixture preparation failed')
            for number, case in enumerate(selected):
                before = library_identity(library['path'])
                if before != library:
                    raise ValueError('Native library changed before original case')
                xml = engine_artifacts/(str(number)+'.xml')
                log = engine_artifacts/(str(number)+'.log')
                try:
                    result = run_isolated([str(executable), '--gtest_filter='+case, '--gtest_output=xml:'+str(xml)], cwd=tree, timeout=a.timeout)
                    log.write_text(result.stdout+result.stderr)
                    outcome = test_outcome(xml, case, result.returncode)
                    exit_code = result.returncode
                except subprocess.TimeoutExpired as error:
                    output = ''.join(value.decode(errors='replace') if isinstance(value, bytes) else value for value in [error.stdout or '', error.stderr or ''])
                    log.write_text(output+'\nOriginal test process group exceeded timeout\n')
                    outcome, exit_code = dict(status='failed', error='Original process-group timeout'), 124
                row = dict(engine=name, name=case, exit=exit_code, log=str(log),
                           native_library_before=before, native_library_after=library_identity(library['path']), **outcome)
                if row['native_library_after'] != before:
                    row.update(status='failed', error='Native library changed during original case')
                report['results'].append(row)
                write_report(a.output, report)
        report['execution_status'] = 'complete'
        report['primary_passed'] = all(not e['unmeasured'] and not e['unsupported_primary'] for e in report['engines']) and bool(report['results']) and all(r['status']=='passed' for r in report['results'])
        # Optional and extended native inventories have not all executed.
        report['passed'] = False
    except Exception as error:
        report.update(execution_status='failed', error=type(error).__name__+': '+str(error))
        print(report['error'], file=sys.stderr)
    finally:
        write_report(a.output, report)
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
