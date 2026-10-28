#!/usr/bin/env python3
"""Exercise real lifecycle facade ordering; selected implementation scope follows its artifact provenance."""
import argparse
import json
from pathlib import Path
import platform
import re
import uuid
from prepare_benchmark import ROOT, clean_environment, sha
from lifecycle_proof import prove_lifecycle
from tools.harness import run_isolated
from tools.native_core import library_identity, verify_loader_output

EXPECTED = ('live-append/front:ABC,DABC\n'
            'copy-failure:published-empty,recovered\n'
            'callback-exception:E,EF\n'
            'clean-capture:hook-published,logger-alive,buffer-alive,then-zero\n'
            'clean-mutation:later-slot-observed-and-destroyed-before-thread\n'
            'thread-clean:fresh-buffer-after-timer,delete-before-null\n'
            'thread-init:allocate,reuse,native-mask-guard,nonmain-block,main-preserve,clean\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True, help='Audited corebase full-library preparation receipt')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--driver', choices=['hooks', 'fork', 'fork-failure', 'init', 'init-host', 'task-directory', 'task-lifetime'], default='hooks')
    parser.add_argument('--require-task-tmp', action='store_true', help='Require the dedicated actual task-directory policy call')
    parser.add_argument('--require-init', action='store_true', help='Require the actual initialization facade path to Rust')
    parser.add_argument('--require-fork', action='store_true', help='Also require both real fork facade paths to Rust')
    parser.add_argument('--require-lifecycle', action='store_true', help='Require all three selected lifecycle facade paths to Rust')
    args = parser.parse_args()
    driver = Path(__file__).with_name({'hooks': 'hook-lifetime.cc', 'fork': 'fork-lifetime.cc', 'fork-failure': 'fork-failure.cc', 'init': 'init-lifetime.cc', 'init-host': 'init-host-effects.cc', 'task-directory': 'task-directory.cc', 'task-lifetime': 'task-directory-lifetime.cc'}[args.driver])
    if args.driver in ['fork-failure', 'init', 'init-host'] and platform.system() != 'Linux':
        parser.error('The controlled executable syscall interposition fixture is Linux-only')
    expected_trace = EXPECTED if args.driver == 'hooks' else (
        'mask0:hook1,pool-new,child-clean,parent-intact\n'
        'mask1:hook1,pool-same,child-clean,parent-intact\n'
        'mask2:hook0,pool-same,child-clean,parent-intact\n'
        'mask3:hook0,pool-same,child-clean,parent-intact\n'
        + ''.join('mask%d:precheck,no-child,no-hook\n' % mask for mask in range(4, 8))
        + 'guards:zero-task-pool,reject-after-returning-coroutine-handler,exec-bypass,precheck-no-fork\n'
        + 'fork-exec:callback,no-hook,pool-same,parent-clean\n')
    if args.driver == 'fork-failure':
        expected_trace = ('fork-fail:two-errors,two-warn-last-errors,two-sleep1,then-parent-no-reset\n'
                          'fork-exec-fail:pid0,no-warning,no-retry,no-callback,no-reset\n')
    if args.driver == 'init-host':
        limits = [0, 1, 1023, 1024, 1048576, 1048576, 1048576, 5, 1048576]
        expected_trace = ''.join(f'case{i}:cpu3,queries2,sockets{limit},fresh-logger,guard-published\n' for i, limit in enumerate(limits))
        expected_trace += 'case9:cpu1,queries1,sockets65535,fresh-logger,guard-published\n'
        expected_trace += 'case10:cpu3,queries2,sockets1024,warning-original-identity,errno-published,continued\n'
    if args.driver == 'task-directory':
        expected_trace = ('empty:out-of-range,no-publication,no-format\n'
            'relative:reject,old-publication\n'
            'existing:accepted,template-published\n'
            'missing:recursive-mkdir,template-published\n'
            'readable-file:accepted-without-directory-check\n'
            'file-parent:reject,old-publication\n'
            'embedded-nul:prefix-checked,raw-string-published\n'
            'embedded-nul-long:raw-length-rejected,published\n'
            'getter-alias:fresh-global-length,publication\n'
            'trailing-slash:double-slash-preserved\n'
            'length255:accepted,created,published\n'
            'length256:rejected,created,published\n'
            'warnings:five-exact-payloads,ordered,no-extras\n'
            'logging-error:no-output,relative-preserves-errno,mkdir-publishes-error,lazy-format,long-publishes\n'
            'logging-none:no-output,relative-preserves-errno,mkdir-publishes-error,lazy-format,long-publishes\n'
            'cleanup:native-globals-cleared\n')
    if args.driver == 'task-lifetime':
        expected_trace = ('string-copy-failure:old-global,recovered\n'
            'length-reject-after-publication\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    attempt = args.output.parent.resolve() / ('corebase-hooks-' + uuid.uuid4().hex)
    attempt.mkdir()
    report = dict(passed=False, scope=__doc__, prepared=str(args.prepared.resolve()),
                  driver=args.driver, attempt=str(attempt), engines={})
    try:
        prepared = json.loads(args.prepared.read_text())
        if not prepared['passed']: raise ValueError('Failed preparation')
        command = prepared['command'].copy()
        source = [i for i, item in enumerate(command) if item.endswith('/benchmark.cc')]
        if len(source) != 1: raise ValueError('Ambiguous driver source')
        command[source[0]] = str(driver)
        if args.driver == 'init-host': command.append('-ldl')
        executable = attempt / 'hook-lifetime'
        command[command.index('-o') + 1] = str(executable)
        command[command.index('-O3')] = '-O0'
        env, report['removed_tracing'] = clean_environment()
        report['compile_command'] = command
        compiled = run_isolated(command, cwd=ROOT, env=env, timeout=60)
        log = attempt / 'compile.log'; log.write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode: raise ValueError('Native driver compile failed')
        report['executable_sha256'] = sha(executable)
        system = platform.system()
        if set(prepared['engines']) != {'native', 'rust'}: raise ValueError('Require exactly native and Rust engines')
        init_baseline = None
        for engine in ['native', 'rust']:
            row = prepared['engines'][engine]
            expected = row['library']
            if library_identity(expected['path']) != expected: raise ValueError('Prepared library changed')
            if args.require_lifecycle or args.require_fork or args.require_init or args.require_task_tmp:
                report.setdefault('lifecycle_proof', {})[engine] = prove_lifecycle(
                    expected['path'], engine == 'rust', attempt / engine, include_fork=args.require_fork, include_init=args.require_init, include_task_tmp=args.require_task_tmp)
            chosen = {**env, **row['measure_environment']}
            setting = 'DYLD_PRINT_LIBRARIES' if system == 'Darwin' else 'LD_TRACE_LOADED_OBJECTS'
            # Linux trace mode exits before main; macOS prints and executes the witness.
            probe_command = [str(executable)]
            if args.driver == 'task-directory':
                probe_command.append(str(attempt / (engine + '-loader-warnings.log')))
            probe = run_isolated(probe_command, cwd=attempt, env={**chosen, setting: '1'}, timeout=30)
            log = attempt / (engine + '-loader.log'); log.write_text(probe.stdout + probe.stderr)
            result = dict(library=expected, passed=False)
            report['engines'][engine] = result
            if probe.returncode: raise ValueError('Loader witness failed')
            result['loader'] = verify_loader_output(probe.stdout + probe.stderr, expected, system)
            check_command = [str(executable)]
            if args.driver == 'task-directory':
                check_command.append(str(attempt / (engine + '-warnings.log')))
            checked = run_isolated(check_command, cwd=attempt, env=chosen, timeout=30)
            log = attempt / (engine + '.log'); log.write_text(checked.stdout + checked.stderr)
            result.update(exit=checked.returncode, trace=checked.stdout)
            if args.driver == 'init':
                lines = checked.stdout.splitlines()
                records = [re.fullmatch(r'case(\d+):threw([01]),calls(\d+),guard1,logger[01],buffer[01],pool[01],sockets\d+,task\d+,bug\d+', line) for line in lines]
                if (len(records) != 24 or any(record is None for record in records)
                        or [int(record[1]) for record in records] != list(range(24))
                        or {record[2] for record in records} != {'0', '1'}):
                    raise ValueError('Incomplete init allocation-prefix witness')
                if engine == 'native':
                    init_baseline = checked.stdout
                expected_trace = init_baseline
                report['init_comparison_scope'] = 'Twenty-four controlled native C++new prefixes, guard/repeated-init invariants independently asserted; exact native/Rust trace comparison. Not system OOM or malloc/sanitizer proof.'
            if checked.returncode or checked.stderr or checked.stdout != expected_trace:
                raise ValueError('Actual native hook lifetime witness failed')
            if library_identity(expected['path']) != expected or sha(executable) != report['executable_sha256']:
                raise ValueError('Artifact changed during witness')
            result['passed'] = True
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    body = json.dumps(report, indent=2) + '\n'
    (attempt / 'report.json').write_text(body); args.output.write_text(body)
    print(json.dumps({k: report.get(k) for k in ('passed', 'error', 'attempt')}))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
