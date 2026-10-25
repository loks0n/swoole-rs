#!/usr/bin/env python3
"""Validate actual PHP-facing core-base consumers and unchanged original PHPTs."""
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from corpus.upstream.run import COMMIT, prepare, record_result, run_cases, save_report
from tools.harness import parse_engines, run_isolated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--fork', action='store_true', help='Actual fork consumer and seven unchanged original Process/guard cases')
    parser.add_argument('--task-directory', action='store_true', help='Actual task_tmpdir settings, file-backed pack/unpack and original unpack case')
    parser.add_argument('--task-directory-fixture-only', action='store_true', help='Explicit preparation only: allow engines whose Task setter is still native')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.fork and args.task_directory:
        parser.error('Choose one consumer cohort')
    if args.task_directory_fixture_only and not args.task_directory:
        parser.error('--task-directory-fixture-only requires --task-directory')
    fixture = Path(__file__).with_name('task-directory.php' if args.task_directory else 'fork-consumers.php' if args.fork else 'consumers.php')
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), upstream_commit=COMMIT,
                  passed=False, execution_status='running', engines=[], results=[], probes=[],
                  native_control_provenance='Observed extension/runtime identity only; no fresh native build attestation.',
                  scope='PHP-reachable type_size/radix/itoa consumers only. Five other helpers have no pinned PHP production callers; native gates cover them.')
    paths = ['tests/swoole_process/coro/set_protocol.phpt',
             'tests/swoole_http_server/chunk.phpt',
             'tests/swoole_http_server/response_create.phpt']
    if args.fork:
        paths = ['tests/swoole_process/' + name + '.phpt' for name in ['start', 'exit', 'wait', 'exec', 'coro/start', 'enable_coroutine']]
        paths += ['tests/swoole_coroutine/new_process.phpt']
        report['scope'] = 'Actual PHP Process normal fork, inherited timer capture cleanup, child/parent logger file ownership, child Zend heap/GC use, coroutine/async-pool rejection, native shutdown and seven unchanged original Process/guard tests. Frozen integrated engine, not isolated M19 or full lifetime/sanitizer/optional-context proof.'
    if args.task_directory:
        paths = ['tests/swoole_server/task/unpack.phpt']
        report.update(task_directory_fixture_only=args.task_directory_fixture_only, fresh_task_php_qualified=False,
            scope='Actual PHP RINIT/task_tmpdir settings, valid file-backed pack/unpack and unchanged original unpack. Default requires seven actual Rust facade paths; explicit fixture-only mode cannot qualify new Rust Task policy.')
    try:
        engines = parse_engines(args.engine, args.php, args.php_extension)
        report['engines'] = [engine.metadata() for engine in engines]
        if {bool(item['rust_feature_bits'] & 8192) for item in report['engines']} != {False, True}:
            raise ValueError('Need native-corebase and Rust-corebase engines verified by actual feature bit8192')
        report['immutable_builds'] = []
        for item in report['engines']:
            if not item['rust_feature_bits'] & 8192:
                continue
            extension = Path(item['extension']).resolve()
            manifest = next((parent / 'build-manifest.json' for parent in list(extension.parents)[:4]
                             if (parent / 'build-manifest.json').is_file()), None)
            if manifest is None:
                raise ValueError('Rust engine requires its immutable build manifest: ' + item['name'])
            build = json.loads(manifest.read_text())
            if (build['build_mode'] != 'immutable' or build['extension_sha256'] != item['sha256']
                    or build['migrated_feature_bits'] != item['rust_feature_bits']
                    or build['inputs']['upstream_commit'] != COMMIT or 'corebase' not in build['inputs']['modules']):
                raise ValueError('Actual extension differs from immutable M19 build identity')
            report['immutable_builds'].append(dict(engine=item['name'], path=str(manifest),
                modules=build['inputs']['modules'], rust_archive_sha256=build['inputs']['rust_archive_sha256']))
        if args.fork or (args.task_directory and not args.task_directory_fixture_only):
            from lifecycle_proof import prove_lifecycle
            proof = args.output.resolve().parent / (args.output.stem + '-proof')
            proof.mkdir(exist_ok=False)
            proof_key = 'fork_policy_proof' if args.fork else 'task_policy_proof'
            report[proof_key + '_directory'] = str(proof)
            report[proof_key] = {}
            for item in report['engines']:
                if args.task_directory and item['rust_feature_bits'] & 8192:
                    symbols = subprocess.check_output(['nm', '-g', item['extension']])
                    (proof / (item['name'] + '-export-preflight.nm')).write_bytes(symbols)
                    if not re.search(rb'\b[Tt] _?swr_v1_corebase_task_tmp_next\s*$', symbols, re.M):
                        raise ValueError('Selected PHP extension lacks dedicated Rust Task policy; fixture preparation requires --task-directory-fixture-only')
            for item in report['engines']:
                report[proof_key][item['name']] = prove_lifecycle(item['extension'],
                    bool(item['rust_feature_bits'] & 8192), proof / item['name'],
                    include_fork=True, include_init=args.task_directory, include_task_tmp=args.task_directory)
        cases = []
        for path in paths:
            original = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{COMMIT}:{path}'])
            cases.append(dict(path=path, module='corebase', sha256=hashlib.sha256(original).hexdigest()))
        image = subprocess.check_output(['git', '-C', str(args.source), 'cat-file', 'blob', f'{COMMIT}:examples/test.jpg'])
        support = [dict(path='examples/test.jpg', sha256=hashlib.sha256(image).hexdigest())]
        report['support_files'] = support
        engine_features = {item['name']: item['rust_feature_bits'] for item in report['engines']}
        if args.fork or args.task_directory:
            if len(engines) != 2: raise ValueError('Comparison requires exactly one native and one Rust engine')
            engines.sort(key=lambda engine: bool(engine_features[engine.name] & 8192))
        guard_baselines = {}
        for engine in engines:
            try:
                probe = run_isolated(engine.command(fixture), timeout=30)
            except subprocess.TimeoutExpired as error:
                decode = lambda value: value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                report['probes'].append(dict(engine=engine.name, returncode=124, timed_out=True,
                    stdout=decode(error.stdout), stderr=decode(error.stderr)))
                raise RuntimeError('PHP consumer timed out; partial output retained')
            report['probes'].append(dict(engine=engine.name, returncode=probe.returncode,
                                         stdout=probe.stdout, stderr=probe.stderr))
            expected = 'M19 PHP task directory consumers OK\n' if args.task_directory else 'M19 PHP fork consumers OK\n' if args.fork else 'M19 PHP consumers OK\n'
            if probe.returncode or probe.stderr or probe.stdout != expected:
                raise RuntimeError('Actual PHP consumer fixture failed; retained result is not a pass')
            if args.task_directory:
                with tempfile.TemporaryDirectory(prefix='swr-corebase-task-startup-') as temporary:
                    directory = Path(temporary) / 'new' / 'child'
                    try:
                        startup = run_isolated(engine.command('-d', 'sys_temp_dir=' + str(directory),
                            fixture, 'startup', str(directory)), timeout=30)
                    except subprocess.TimeoutExpired as error:
                        decode = lambda value: value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                        report['probes'].append(dict(engine=engine.name, mode='task-startup', returncode=124,
                            timed_out=True, stdout=decode(error.stdout), stderr=decode(error.stderr)))
                        raise RuntimeError('PHP task startup timed out; partial output retained')
                    report['probes'].append(dict(engine=engine.name, mode='task-startup', returncode=startup.returncode,
                        stdout=startup.stdout, stderr=startup.stderr))
                    if (startup.returncode or startup.stderr or startup.stdout != 'M19 PHP task directory startup OK\n'
                            or directory.exists()):
                        raise RuntimeError('Actual PHP task startup/cleanup failed; result retained')
                warning = args.output.resolve().parent / (args.output.stem + '-errors') / (engine.name + '.log')
                warning.parent.mkdir(exist_ok=True)
                try:
                    rejected = run_isolated(engine.command(fixture, 'settings-error', str(errno.ENOTDIR), warning), timeout=30)
                except subprocess.TimeoutExpired as error:
                    decode = lambda value: value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                    report['probes'].append(dict(engine=engine.name, mode='task-settings-error', returncode=124,
                        timed_out=True, stdout=decode(error.stdout), stderr=decode(error.stderr)))
                    raise RuntimeError('PHP task error consumer timed out; partial output retained')
                report['probes'].append(dict(engine=engine.name, mode='task-settings-error', returncode=rejected.returncode,
                    stdout=rejected.stdout, stderr=rejected.stderr, expected_enotdir=errno.ENOTDIR,
                    warning_log=str(warning)))
                if (rejected.returncode or rejected.stderr or rejected.stdout != 'M19 PHP task directory errors OK\n'
                        or not warning.is_file()):
                    raise RuntimeError('Actual PHP task rejection consumer failed; result retained')
            if args.fork:
                logger_fixture = Path(__file__).with_name('fork-logger.php')
                logger_root = args.output.resolve().parent / (args.output.stem + '-logger') / engine.name
                logger_root.mkdir(parents=True, exist_ok=False)
                try:
                    logger = run_isolated(engine.command(logger_fixture, logger_root), timeout=30)
                except subprocess.TimeoutExpired as error:
                    decode = lambda value: value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                    report['probes'].append(dict(engine=engine.name, mode='fork-logger', returncode=124,
                        timed_out=True, stdout=decode(error.stdout), stderr=decode(error.stderr), artifacts=str(logger_root)))
                    raise RuntimeError('PHP fork logger timed out; partial output and existing raw files retained')
                raw_logs = sorted(str(path) for path in logger_root.rglob('*.log'))
                report['probes'].append(dict(engine=engine.name, mode='fork-logger', returncode=logger.returncode,
                    stdout=logger.stdout, stderr=logger.stderr, artifacts=str(logger_root), raw_logs=raw_logs))
                if logger.returncode or logger.stderr or logger.stdout != 'M19 PHP fork logger ownership OK\n' or len(raw_logs) != 4:
                    raise RuntimeError('Actual PHP fork logger ownership failed; raw files retained')
                for mode, message in [('coroutine', 'must be forked outside the coroutine'),
                                      ('async', 'can not fork after using async-threads')]:
                    try:
                        guard = run_isolated(engine.command(fixture, mode), timeout=30)
                    except subprocess.TimeoutExpired as error:
                        decode = lambda value: value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                        report['probes'].append(dict(engine=engine.name, mode=mode, returncode=124, timed_out=True,
                            stdout=decode(error.stdout), stderr=decode(error.stderr)))
                        raise RuntimeError('PHP fork guard timed out; partial output retained: ' + mode)
                    record = dict(engine=engine.name, mode=mode, returncode=guard.returncode,
                                  stdout=guard.stdout, stderr=guard.stderr)
                    report['probes'].append(record)
                    if (guard.returncode != 255 or guard.stderr or
                            not guard.stdout.startswith('\nFatal error: Uncaught Swoole\\Error: ' + message + ' in ')
                            or '\nStack trace:\n' not in guard.stdout
                            or 'Swoole\\Process->start()' not in guard.stdout
                            or 'thrown in ' not in guard.stdout):
                        raise RuntimeError('Actual PHP fatal fork guard failed: ' + mode)
                    if not engine_features[engine.name] & 8192:
                        guard_baselines[mode] = guard.stdout
                    elif guard_baselines.get(mode) != guard.stdout:
                        raise RuntimeError('PHP fatal guard differs from exact native output: ' + mode)
            with tempfile.TemporaryDirectory(prefix='swr-corebase-php-') as temporary:
                sandbox = Path(temporary)
                prepare(args.source, sandbox, cases, support)
                (sandbox / 'home').mkdir()
                (sandbox / 'tmp').mkdir()
                artifacts = args.output.resolve().parent / (args.output.stem + '-artifacts') / engine.name
                results, _ = run_cases(engine, cases, sandbox, artifacts, 30, 1)
                for case in cases:
                    record_result(report, engine, case, results[case['path']])
                save_report(args.output, report)
        report.update(execution_status='complete', passed=all(r['status'] == 'passed' for r in report['results']))
        if args.task_directory:
            report['fresh_task_php_qualified'] = report['passed'] and not args.task_directory_fixture_only
    except Exception as error:
        report.update(execution_status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        save_report(args.output, report)
    print(json.dumps({k: report[k] for k in ['passed', 'execution_status', 'probes']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
