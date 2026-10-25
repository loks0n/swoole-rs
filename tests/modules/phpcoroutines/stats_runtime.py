#!/usr/bin/env python3
"""Actual read-only PHP statistics, idle queries or startup catalogue; no frontend instances/callback/IO creation."""
import argparse
import json
from pathlib import Path
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, parse_engines, run_isolated, write_report
from tools.hybrid_identity import attest, sha

BIT = 134217728


def validate_projection(manifest, patch, rust_sha):
    if manifest['inputs']['rust_sources_sha256'].get('crates/phpcoroutines/src/stats.rs') != rust_sha:
        raise ValueError('Production archive lacks the qualified statistics Rust source')
    required = b'+        const auto plan = swr_v1_phpcoroutines_stats(&state, observation, has_iouring);'
    if required not in patch.splitlines():
        raise ValueError('Production overlay lacks the actual Rust statistics caller')


QUERY_HEADER_MARKERS = [
    b'+            switch (swr_v1_phpcoroutines_stack_step(&state, observation, bytes)) {',
    b'+        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_ACTIVE, 0, activated)',
    b'+        if (!swr_v1_phpcoroutines_scheduler_policy(SWR_CORO_SCHED_ENABLE, ctx != nullptr,',
    b'+        if (!swr_v1_phpcoroutines_scheduler_policy(SWR_CORO_SCHED_DISABLE, ctx != nullptr,',
]
QUERY_BINDING_MARKER = b'+    if (swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_PARENT, nullptr, cid, ret) == SWR_CORO_QUERY_FALSE) {'
QUERY_OLD_ACTIVE = b'+        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_ACTIVE, 0, activated)'
ACTIVATED_HEADER_MARKERS = [
    b'+    static SW_THREAD_LOCAL swr_phpcoroutines_activation_state activated;',
    b'+        return swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_READ);',
    b'+                   ? Coroutine::get_current_cid() : -1;',
    b'+                   ? Coroutine::get_elapsed(cid) : -1;',
    b'+                   ? Coroutine::get_execute_time(cid) : -1;',
]
ACTIVATED_CPP_MARKERS = [
    b'+SW_THREAD_LOCAL swr_phpcoroutines_activation_state PHPCoroutine::activated{0};',
    b'+            swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_START);',
    b'+    swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_STOP);',
]


METADATA_HEADER_MARKERS = [
    b'+    swr_phpcoroutines_scheduler_phase enable_scheduler;',
    b'+        return swr_v1_phpcoroutines_metadata(&stage, SWR_CORO_METADATA_ENABLE, &cells, 0, 0).value != 0;',
    b'+        return swr_v1_phpcoroutines_metadata(&stage, SWR_CORO_METADATA_DISABLE, &cells, 0, 0).value != 0;',
    b'+        return static_cast<long>(swr_v1_phpcoroutines_metadata(&stage, SWR_CORO_METADATA_PARENT, &cells, 0, 0).value);',
]


def validate_queries_projection(manifest, patch, header, rust_sha, phase_sha=None, metadata_sha=None):
    if manifest['inputs']['rust_sources_sha256'].get('crates/phpcoroutines/src/context.rs') != rust_sha:
        raise ValueError('Production archive lacks the qualified common/query Rust source')
    legacy = (QUERY_OLD_ACTIVE in header.splitlines()
              and ACTIVATED_HEADER_MARKERS[0] not in header.splitlines())
    required = QUERY_HEADER_MARKERS if legacy else [marker for marker in QUERY_HEADER_MARKERS if marker != QUERY_OLD_ACTIVE] + ACTIVATED_HEADER_MARKERS
    metadata = METADATA_HEADER_MARKERS[0] in header.splitlines()
    if metadata:
        required = [marker for marker in required if marker not in QUERY_HEADER_MARKERS[2:]] + METADATA_HEADER_MARKERS
        if metadata_sha is None or manifest['inputs']['rust_sources_sha256'].get('crates/phpcoroutines/src/context_metadata.rs') != metadata_sha:
            raise ValueError('Production archive lacks the qualified context metadata source')
    if QUERY_BINDING_MARKER not in patch.splitlines() or any(marker not in header.splitlines() for marker in required):
        raise ValueError('Production overlay lacks actual selected query/header callers')
    if not legacy:
        if phase_sha is None or manifest['inputs']['rust_sources_sha256'].get('crates/phpcoroutines/src/scheduler_phase.rs') != phase_sha:
            raise ValueError('Production archive lacks the qualified activated-state phase source')
        if any(marker not in patch.splitlines() for marker in ACTIVATED_CPP_MARKERS):
            raise ValueError('Production overlay lacks constant activated custody/publications')


METHOD_PROJECTION_MARKER = b'+        const auto method = swr_v1_phpcoroutines_method(&cursor, kind, capabilities,'
METHOD_TABLES = [[(0, 'swoole_coroutine_methods', 39), (1, 'swoole_exit_exception_methods', 3)],
                 [(2, 'swoole_coroutine_scheduler_methods', 6)], [(3, 'swoole_coroutine_system_methods', 13)]]


def validate_startup_projection(manifest, patches, rust_sha, method_sha=None):
    if len(patches) != 3:
        raise ValueError('Require all three native startup overlays')
    if manifest['inputs']['rust_sources_sha256'].get('crates/phpcoroutines/src/bootstrap.rs') != rust_sha:
        raise ValueError('Production archive lacks the qualified startup catalogue Rust source')
    for kind, patch in enumerate(patches):
        required = ('+        const auto plan = swr_v1_phpcoroutines_bootstrap(&state, '
                    + str(kind) + ', observation, exit_opcode);').encode()
        if required not in patch.splitlines():
            raise ValueError('Production overlay lacks actual startup caller kind ' + str(kind))
    if any(METHOD_PROJECTION_MARKER in patch.splitlines() for patch in patches):
        if method_sha is None or manifest['inputs']['rust_sources_sha256'].get('crates/phpcoroutines/src/method_catalogue.rs') != method_sha:
            raise ValueError('Production archive lacks the qualified whole method catalogue')
        for patch, tables in zip(patches, METHOD_TABLES):
            if METHOD_PROJECTION_MARKER not in patch.splitlines():
                raise ValueError('Production overlay lacks real typed method projector')
            for kind, table, capacity in tables:
                declaration = f'+static zend_function_entry {table}[{capacity}]{{}};'.encode()
                caller = f'php_coroutine_project_methods({kind}, {table}_bindings, {table});'.encode()
                if declaration not in patch.splitlines() or not any(line.startswith(b'+') and caller in line for line in patch.splitlines()):
                    raise ValueError('Production overlay lacks stable method storage and actual MINIT caller ' + table)



CONFIG_HEADER_MARKERS = [
    b'+        return swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_MAX, 0);',
    b'+        swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_MAX, n);',
    b'+        swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_DEADLOCK, value);',
    b'+        return static_cast<uint32_t>(swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_HOOKS, 0));',
    b'+        swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_PREEMPTIVE, value);',
    b'+    static SW_THREAD_LOCAL swr_phpcoroutines_config_state config;',
]
CONFIG_CPP_MARKERS = [
    b'+SW_THREAD_LOCAL swr_phpcoroutines_config_state PHPCoroutine::config{',
    b'+    SW_DEFAULT_MAX_CORO_NUM, 0, 0, 0,',
    b'+    swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_HOOKS, flags);',
]


def validate_config_projection(manifest, patch, header, rust_sha):
    if manifest['inputs']['rust_sources_sha256'].get('crates/phpcoroutines/src/config_state.rs') != rust_sha:
        raise ValueError('Production archive lacks the qualified Config Rust state')
    if any(marker not in patch.splitlines() for marker in CONFIG_CPP_MARKERS) or any(marker not in header.splitlines() for marker in CONFIG_HEADER_MARKERS):
        raise ValueError('Production overlay lacks actual config custody and callers')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('statistics', 'idle-queries', 'startup', 'configuration'), default='statistics')
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture = Path(__file__).with_name({'statistics': 'statistics.php', 'idle-queries': 'idle_queries.php', 'startup': 'startup.php', 'configuration': 'configuration.php'}[args.profile])
    report = dict(passed=False, scope=__doc__, profile=args.profile,
                  fixture_sha256=sha(fixture), engines=[], results=[],
                  reference_build_attestation=False, measurement_performed=False,
                  limits=['Ordinary idle counters/order/types only; active reactor/async/ring configurations unqualified.',
                          'No callback/context lifetime, full175 originals, ZTS/configuration union or performance claim.'])
    try:
        engines = parse_engines(args.engine, args.php, args.php_extension)
        report['engines'] = [engine.metadata() for engine in engines]
        selected = [item for item in report['engines'] if item['rust_feature_bits'] & BIT]
        native = [item for item in report['engines'] if item['rust_feature_bits'] == 0]
        if len(engines) != 2 or len(selected) != 1 or len(native) != 1 or selected[0]['rust_bridge_abi'] != 1:
            raise ValueError('Require exactly native and ABI1/M29-selected engines')
        report['source_attestation'] = attest(args.build_manifest, args.archive, selected[0], args.source_ref, BIT)
        patch_path = 'migration/patches/phpcoroutines/0002-user-yield-registry.patch'
        patch = subprocess.check_output(['git', 'show', report['source_attestation']['source_ref'] + ':' + patch_path], cwd=ROOT)
        rust_path = 'crates/phpcoroutines/src/' + {'statistics': 'stats.rs', 'idle-queries': 'context.rs', 'startup': 'bootstrap.rs', 'configuration': 'config_state.rs'}[args.profile]
        rust_sha = sha(ROOT / rust_path)
        if args.profile == 'statistics':
            validate_projection(json.loads(args.build_manifest.read_text()), patch, rust_sha)
        elif args.profile == 'idle-queries':
            header_path = 'migration/patches/phpcoroutines/0004-deferred-context-header.patch'
            header = subprocess.check_output(['git', 'show', report['source_attestation']['source_ref'] + ':' + header_path], cwd=ROOT)
            validate_queries_projection(json.loads(args.build_manifest.read_text()), patch, header, rust_sha,
                                        sha(ROOT / 'crates/phpcoroutines/src/scheduler_phase.rs'),
                                        sha(ROOT / 'crates/phpcoroutines/src/context_metadata.rs'))
            report['limits'] += ['Only idle public getters, positive live VM stack accounting and absent-current scheduler admission; context object initialization/GC/getContext, active scheduler/interrupt/clocks and ZTS are unqualified.']
            if QUERY_OLD_ACTIVE not in header.splitlines():
                report['limits'] += ['New activated-state header call paths require compiled primitive-phase identity and constant seed/publication markers. Idle values do not directly expose the private activated byte or qualify actual activation/teardown.']
        elif args.profile == 'configuration':
            header = subprocess.check_output(['git', 'show', report['source_attestation']['source_ref'] + ':migration/patches/phpcoroutines/0004-deferred-context-header.patch'], cwd=ROOT)
            validate_config_projection(json.loads(args.build_manifest.read_text()), patch, header, rust_sha)
            report['limits'] += ['Only ordinary primitive setter call paths and Native options publication/order; private Rust values and future activation/admission effects are not observed by getOptions. Actual threads/ZTS/hooks/lifetime remain unqualified.']
        else:
            patches = [patch]
            for name in ('0001-scheduler-queue.patch', '0003-system-file-admission.patch'):
                patches.append(subprocess.check_output(['git', 'show', report['source_attestation']['source_ref'] + ':migration/patches/phpcoroutines/' + name], cwd=ROOT))
            validate_startup_projection(json.loads(args.build_manifest.read_text()), patches, rust_sha,
                                        sha(ROOT / 'crates/phpcoroutines/src/method_catalogue.rs'))
            if any(METHOD_PROJECTION_MARKER in patch.splitlines() for patch in patches):
                report['limits'] += ['Whole method catalogue source, stable Native projection and all real MINIT callers are attested. Existing startup reflection observes method names/modifiers/declaring classes; actual handler invocation/argument semantics/reinit/ZTS/lifetime remain unqualified.']
            report['limits'] += ['Only loaded startup class/alias/parent/method/default-property/constant catalogue and order at shortnames off/on; opcode/autoload hooks, object construction/destruction, handler behavior and non-CLI/PHP-version/ZTS union remain unqualified.']
        report[{'statistics': 'statistics_projection', 'idle-queries': 'query_projection', 'startup': 'startup_projection', 'configuration': 'configuration_projection'}[args.profile]] = dict(rust_path=rust_path, rust_sha256=rust_sha, actual_caller_verified=True)
        configurations = (0, 1) if args.profile == 'startup' else (None,)
        for shortnames in configurations:
            for engine, identity in zip(engines, report['engines']):
                arguments = [str(fixture)] if shortnames is None else ['-d', 'swoole.use_shortname=' + str(shortnames), str(fixture), str(shortnames)]
                result = run_isolated(engine.command(*arguments), timeout=30)
                row = dict(engine=engine.name, exit=result.returncode, stdout=result.stdout,
                           stderr=result.stderr, extension_sha256_after=sha(identity['extension']), passed=False)
                if shortnames is not None: row['shortnames'] = shortnames
                report['results'].append(row)
                if result.returncode == 0 and not result.stderr and row['extension_sha256_after'] == identity['sha256']:
                    try:
                        row['summary'] = json.loads(result.stdout)
                        row['passed'] = True
                    except ValueError as error:
                        row['parse_error'] = str(error)
                write_report(args.output, report)
        if not all(row['passed'] for row in report['results']):
            raise ValueError('Read-only witness failed; original per-engine outputs retained')
        for index in range(0, len(report['results']), 2):
            if report['results'][index]['summary'] != report['results'][index + 1]['summary']:
                raise ValueError('Native/selected read-only values or field order differ')
        receipt = report['source_attestation']
        if (sha(args.build_manifest) != receipt['manifest_sha256'] or sha(args.archive) != receipt['archive_sha256']
                or sha(fixture) != report['fixture_sha256']):
            raise ValueError('Immutable source receipt/archive/fixture changed')
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    write_report(args.output, report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'error')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
