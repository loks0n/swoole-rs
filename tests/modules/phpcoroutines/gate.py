#!/usr/bin/env python3
"""Matched ordinary Scheduler bodies with inert native effect recorders; no PHP/IO/callback execution."""
import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report
from make_patches import DEST, SOURCE_SHA, body, header_selected, HEADER_DEST, HEADER_SIGNATURES


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(source, work, destination=DEST):
    original = (source / destination).read_text()
    expected = {DEST: SOURCE_SHA, 'ext-src/swoole_coroutine.cc': '1707e8d7a2881a50b2aca203681afe459a70281929fc29057e9752c71b2ada58', 'ext-src/swoole_coroutine_system.cc': '1b2a3d669d95bc7e524787c254ecb38467fa5e2050c1544b360f54e0cbc8c869'}[destination]
    if hashlib.sha256(original.encode()).hexdigest() != expected:
        raise ValueError('Pinned source checksum mismatch')
    folder = ROOT / 'migration/patches/phpcoroutines'
    manifest = json.loads((folder / 'manifest.json').read_text())
    patch = next(item for item in manifest['patches'] if item['upstream_paths'] == [destination])
    if patch['upstream_paths'] != [destination] or sha(folder / patch['path']) != patch['sha256']:
        raise ValueError('Patch identity mismatch')
    target = work / destination
    target.parent.mkdir(parents=True)
    target.write_text(original)
    result = run_isolated(['patch', '-p1', '-i', str(folder / patch['path'])], cwd=work, timeout=20)
    if result.returncode:
        raise ValueError('Overlay failed: ' + result.stdout + result.stderr)
    return original, target.read_text()


def validate_abi(identity):
    if type(identity.get('abi')) is not int or identity['abi'] != 1:
        raise ValueError('Supplied archive ABI version mismatch')
    bits = identity.get('bits')
    if type(bits) is not int or not 0 <= bits < 1 << 64 or not bits & 134217728:
        raise ValueError('Supplied archive lacks phpcoroutines feature bit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path, help='Use an immutable selected FFI archive, validating real ABI/feature exports')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--rust-sanitize', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    work = output.parent / ('phpcoroutines-gate-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, work=str(work), commands=[], scope=__doc__,
                  measurement_performed=False, runtime_executed=False,
                  limits=['Native payload releases/coroutine creation/IO are trace-only inert stubs.',
                          'Free-object/shutdown/error/bailout branches are not executed.',
                          'No actual PHP or originals, no ownership/lifetime or performance claim.'])
    def run(command, timeout=120, env=None):
        require_build_space(ROOT)
        result = run_isolated(command, timeout=timeout, env=env)
        report['commands'].append(dict(command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        if result.returncode:
            raise ValueError('Command failed; original outcome retained')
        return result
    try:
        original, selected = stage(args.source, work / 'overlay')
        rust = ROOT / 'crates/phpcoroutines/src/lib.rs'
        report['rust_sources_sha256'] = {str(path.relative_to(ROOT)): sha(path)
            for path in sorted((ROOT / 'crates/phpcoroutines').rglob('*')) if path.is_file()}
        if args.archive:
            if args.rust_sanitize:
                raise ValueError('--rust-sanitize cannot instrument a supplied archive')
            archive = args.archive.resolve(strict=True)
            report['archive_identity'] = dict(mode='supplied selected FFI archive', path=str(archive),
                source_attested_here=False, rust_instrumentation_requested=False,
                source_attestation_limit='Caller source hashes are recorded separately; production manifest must bind the supplied archive to its source.')
        else:
            archive = work / 'libphpcoroutines.a'
            command = ['rustc', '--edition=2024', '--crate-name', 'swoole_rs_phpcoroutines', '--crate-type', 'staticlib', '-C', 'opt-level=2', str(rust), '-o', str(archive)]
            env = os.environ.copy()
            if args.rust_sanitize:
                env['RUSTC_BOOTSTRAP'] = '1'
                command += ['-Zsanitizer=address', '-C', 'debuginfo=1']
            run(command, env=env)
            report['archive_identity'] = dict(mode='fresh module-only staticlib', path=str(archive),
                source_attested_here=True, rust_instrumentation_requested=args.rust_sanitize)
        report['archive_sha256'] = sha(archive)
        if args.archive:
            probe = work / 'archive-identity.cc'
            probe.write_text("""#include <cstdio>
#include "swoole_rs.h"
int main() {
    std::printf("{\\"abi\\":%u,\\"bits\\":%llu}\\n", swr_v1_abi_version(),
                static_cast<unsigned long long>(swr_v1_feature_bits()));
}
""")
            # Identity is queried from the exact linked archive, never inferred from its filename.
            binary = work / 'archive-identity'
            run([os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror',
                 '-I' + str(ROOT / 'native/include'), str(probe), str(archive), '-lpthread', '-ldl', '-lm', '-o', str(binary)])
            result = run([str(binary)])
            identity = json.loads(result.stdout)
            report['archive_identity']['observed_abi'] = identity
            validate_abi(identity)
        if args.rust_sanitize:
            members = run(['ar', 't', str(archive)]).stdout.splitlines()
            own = [name for name in members if name.startswith('libphpcoroutines.swoole_rs_phpcoroutines.')]
            if not own:
                raise ValueError('No owned Rust object found for sanitizer observation')
            observations = []
            for member in own:
                import subprocess
                data = subprocess.run(['ar', 'p', str(archive), member], capture_output=True, check=True).stdout
                obj = work / member
                obj.write_bytes(data)
                symbols = run(['nm', '-u', str(obj)])
                observations.append(dict(member=member, asan_imports=[line for line in symbols.stdout.splitlines() if '__asan_' in line]))
            if not any(row['asan_imports'] for row in observations):
                raise ValueError('Owned Rust objects lack ASan instrumentation imports')
            report['rust_asan_object_observations'] = observations
        outputs = []
        for feature, source in [('native', original), ('selected', selected)]:
            types = source[source.index('struct SchedulerTask {'):source.index('static zend_class_entry *')]
            add_sig = 'static void scheduler_add_task(SchedulerObject *s, SchedulerTask *task' + (', zend_long count) {' if feature == 'selected' else ') {')
            start_sig = 'static PHP_METHOD(swoole_coroutine_scheduler, start) {'
            fixture = (ROOT / 'tests/modules/phpcoroutines/ordinary.cc').read_text().replace('// ACTUAL_TYPES', types).replace(
                '// ACTUAL_ADD', add_sig + body(source, add_sig) + '}').replace('// ACTUAL_START', start_sig + body(source, start_sig) + '}')
            cpp, binary = work / (feature + '.cc'), work / feature
            cpp.write_text(fixture)
            flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            outputs.append(result.stdout)
        if outputs[0] != outputs[1]:
            raise ValueError('Native and selected effect traces differ')
        for global_mode in (False, True):
            mode = 'global' if global_mode else 'thread'
            registry_outputs = []
            for feature in ('native', 'selected'):
                binary = work / ('registry-' + mode + '-' + feature)
                flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
                command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                           '-I' + str(ROOT / 'native/phpcoroutines'), str(ROOT / 'tests/modules/phpcoroutines/registry.cc'),
                           '-pthread', '-DSWR_REGISTRY_GLOBAL=' + str(int(global_mode)), '-o', str(binary)]
                if feature == 'selected':
                    command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-ldl', '-lm']
                run(command)
                result = run([str(binary)])
                registry_outputs.append(result.stdout)
                report['registry_' + mode + '_' + feature] = dict(stdout=result.stdout)
            if registry_outputs[0] != registry_outputs[1]:
                raise ValueError('Native and Rust metadata model results differ in ' + mode + ' profile')
        report['registry_models'] = dict(matched=True, opaque_records_per_profile=4096,
                                        profiles=['SW_THREAD off: global state', 'SW_THREAD on: per-thread state'],
                                        sequential_global_thread_handoff=True, thread_independence=True,
                                        duplicate_zero_extreme_keys=True, actual_coroutine_operations=False)
        system_outputs = []
        system_original, system_selected = stage(args.source, work / 'system-overlay', 'ext-src/swoole_coroutine_system.cc')
        for feature, source in [('native', system_original), ('selected', system_selected)]:
            bodies = []
            for name in ('readFile', 'writeFile', 'statvfs', 'sleep', 'getaddrinfo'):
                signature = 'PHP_METHOD(swoole_coroutine_system, ' + name + ') {'
                bodies.append(signature + body(source, signature) + '}')
            signature = 'PHP_FUNCTION(swoole_coroutine_gethostbyname) {'
            bodies.append(signature + body(source, signature) + '}')
            fixture = (ROOT / 'tests/modules/phpcoroutines/system.cc').read_text().replace('// ACTUAL_BODIES', '\n'.join(bodies))
            cpp, binary = work / ('system-' + feature + '.cc'), work / ('system-' + feature)
            cpp.write_text(fixture)
            flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            system_outputs.append(result.stdout)
            report['system_' + feature] = dict(stdout=result.stdout)
        if system_outputs[0] != system_outputs[1]:
            raise ValueError('Native and selected System body traces differ')
        report['system_models'] = dict(matched=True, flag_cases=7, normal_native_stub_calls=20, address_family_profiles=2,
                                      timer_scalar_comparisons=7, actual_filesystem_or_sleep=False)
        option_outputs = []
        for feature, source in [('native', original), ('selected', selected)]:
            signature = 'void php_swoole_set_coroutine_option(zend_array *vht) {'
            fixture = (ROOT / 'tests/modules/phpcoroutines/options.cc').read_text().replace('// ACTUAL_BODY', signature + body(source, signature) + '}')
            cpp, binary = work / ('options-' + feature + '.cc'), work / ('options-' + feature)
            cpp.write_text(fixture)
            flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            option_outputs.append(result.stdout)
        if option_outputs[0] != option_outputs[1]:
            raise ValueError('Native and selected option traces differ')
        report['option_models'] = dict(matched=True, configurations=1024, null_alias_precedence=True,
                                      max_nonpositive_default=True, native_effects='inert lookup/value/setter/merge/resolver stubs')
        create_outputs = []
        coroutine_original, coroutine_selected = stage(args.source, work / 'create-overlay', 'ext-src/swoole_coroutine.cc')
        for feature, source in [('native', coroutine_original), ('selected', coroutine_selected)]:
            signature = 'long PHPCoroutine::create(zend_fcall_info_cache *fci_cache, uint32_t argc, zval *argv, zval *callable) {'
            fixture = (ROOT / 'tests/modules/phpcoroutines/create.cc').read_text().replace('// ACTUAL_BODY', signature + body(source, signature) + '}')
            cpp, binary = work / ('create-' + feature + '.cc'), work / ('create-' + feature)
            cpp.write_text(fixture)
            flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            create_outputs.append(result.stdout)
            report['create_' + feature] = dict(stdout=result.stdout)
        if create_outputs[0] != create_outputs[1]:
            raise ValueError('Native and selected create admission traces differ')
        report['create_models'] = dict(matched=True, normal_create_calls=4, native_activation_stubs=2,
                                      pointer_or_type_errors='pure copied scalar decisions only, no native error branch executed',
                                      actual_coroutine_execution=False)
        for iouring in (False, True):
            stats_outputs = []
            for feature, source in [('native', coroutine_original), ('selected', coroutine_selected)]:
                signature = 'static PHP_METHOD(swoole_coroutine, stats) {'
                fixture = (ROOT / 'tests/modules/phpcoroutines/stats.cc').read_text().replace('// ACTUAL_BODY', signature + body(source, signature) + '}')
                name = 'stats-' + str(int(iouring)) + '-' + feature
                cpp, binary = work / (name + '.cc'), work / name
                cpp.write_text(fixture)
                command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                           '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
                if iouring:
                    command += ['-DSW_USE_IOURING=1']
                if feature == 'selected':
                    command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
                run(command)
                result = run([str(binary)])
                stats_outputs.append(result.stdout)
            if stats_outputs[0] != stats_outputs[1]:
                raise ValueError('Native and selected statistics traces differ')
        report['stats_models'] = dict(matched=True, configurations=16, iouring_build_profiles=2,
                                     native_effects='inert getters and Zend publication; no runtime counters or IO queried')
        deferred_outputs = []
        owner_signature = 'struct PHPCoroutineDeferredTasks {'
        owner = 'namespace swoole { ' + owner_signature + body(coroutine_selected, owner_signature) + '}; }'
        for feature, source in [('native', coroutine_original), ('selected', coroutine_selected)]:
            signature = 'void PHPCoroutine::defer(zend::Function *fci) {'
            fixture = (ROOT / 'tests/modules/phpcoroutines/deferred.cc').read_text().replace('// SELECTED_OWNER', owner if feature == 'selected' else '').replace('// ACTUAL_BODY', signature + body(source, signature) + '}')
            cpp, binary = work / ('deferred-' + feature + '.cc'), work / ('deferred-' + feature)
            cpp.write_text(fixture)
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            deferred_outputs.append(result.stdout)
        if deferred_outputs[0] != deferred_outputs[1]:
            raise ValueError('Native and selected deferred metadata order differs')
        report['deferred_models'] = dict(matched=True, lifo_records=4096, insertion_after_pop=2,
                                        native_callbacks=False, actual_lifecycle=False, failure_injection=False)
        configure_outputs = []
        for feature, source in [('native', original), ('selected', selected)]:
            signature = 'PHP_METHOD(swoole_coroutine_scheduler, set) {'
            fixture = (ROOT / 'tests/modules/phpcoroutines/configure.cc').read_text().replace('// ACTUAL_BODY', signature + body(source, signature) + '}')
            cpp, binary = work / ('configure-' + feature + '.cc'), work / ('configure-' + feature)
            cpp.write_text(fixture)
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            configure_outputs.append(result.stdout)
        if configure_outputs[0] != configure_outputs[1]:
            raise ValueError('Native and selected Scheduler configuration traces differ')
        report['configure_models'] = dict(matched=True, configurations=64, native_callbacks=False,
                                         cache_creation='inert successful records only; native invalid/failure/removal branch unexecuted')
        activation_outputs = []
        for feature, source in [('native', coroutine_original), ('selected', coroutine_selected)]:
            signature = 'void PHPCoroutine::activate() {'
            fixture = (ROOT / 'tests/modules/phpcoroutines/activation.cc').read_text().replace('// ACTUAL_BODY', signature + body(source, signature) + '}')
            cpp, binary = work / ('activation-' + feature + '.cc'), work / ('activation-' + feature)
            cpp.write_text(fixture)
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            activation_outputs.append(result.stdout)
        if activation_outputs[0] != activation_outputs[1]:
            raise ValueError('Native and selected ordinary activation policy traces differ')
        report['activation_models'] = dict(matched=True, configurations=96, global_local_short_circuit=True,
                                          actual_php_library_hooks_threads_core_callbacks=False,
                                          destroy_callback='inert registration record only; never invoked')
        query_outputs = []
        report['context_query'] = dict(object_configurations=6, positive_parent_results=6, nonnegative_stack_results=6,
            actual_zend_gc_coroutine=False, native_error_warning_or_lifecycle=False)
        signatures = ['static PHP_METHOD(swoole_coroutine, getContext) {',
                      'PHP_METHOD(swoole_coroutine, getPcid) {', 'static PHP_METHOD(swoole_coroutine, getStackUsage) {']
        for feature, source in [('native', coroutine_original), ('selected', coroutine_selected)]:
            definitions = '\n'.join(signature + body(source, signature) + '}' for signature in signatures)
            fixture = (ROOT / 'tests/modules/phpcoroutines/context-query.cc').read_text().replace('// ACTUAL_QUERY_BODIES', definitions)
            cpp, binary = work / ('context-query-' + feature + '.cc'), work / ('context-query-' + feature)
            cpp.write_text(fixture)
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            query_outputs.append(result.stdout)
        if query_outputs[0] != query_outputs[1]:
            raise ValueError('Native and selected ordinary context binding traces differ')
        report['context_query']['matched'] = True
        trace_outputs = []
        report['introspection'] = dict(exact_bodies=2, ordinary_configurations=12, executor_restoration_checked=True,
            actual_zend_vm_trace_gc_or_output=False, native_error_or_lifecycle=False)
        signatures = ['static PHP_METHOD(swoole_coroutine, getBackTrace) {',
            'void sw_php_print_backtrace(zend_long cid, zend_long options, zend_long limit, zval *return_value) {']
        for feature, source in [('native', coroutine_original), ('selected', coroutine_selected)]:
            definitions = '\n'.join(signature + body(source, signature) + '}' for signature in signatures)
            fixture = (ROOT / 'tests/modules/phpcoroutines/introspection.cc').read_text().replace('// ACTUAL_TRACE_BODIES', definitions)
            cpp, binary = work / ('introspection-' + feature + '.cc'), work / ('introspection-' + feature)
            cpp.write_text(fixture)
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            trace_outputs.append(result.stdout)
        if trace_outputs[0] != trace_outputs[1]:
            raise ValueError('Native and selected introspection routing/restoration traces differ')
        report['introspection']['matched'] = True
        report['bootstrap'] = dict(ordinary_configurations_per_version=24, php_version_capabilities=[80300,80400],
            actual_zend_classes_opcodes_or_callbacks=False,
            method_projection='Inert Native effect stub only; real table projector separately qualified by methods.py')
        signatures = [('void php_swoole_coroutine_minit(int module_number) {', coroutine_original, coroutine_selected),
            ('void php_swoole_coroutine_scheduler_minit(int module_number) {', original, selected),
            ('void php_swoole_coroutine_system_minit(int module_number) {', system_original, system_selected)]
        for version in (80300,80400):
            outputs = []
            for feature in ('native','selected'):
                definitions = '\n'.join(signature + body(native if feature=='native' else overlay, signature) + '}'
                    for signature,native,overlay in signatures)
                fixture = (ROOT / 'tests/modules/phpcoroutines/bootstrap.cc').read_text().replace('// ACTUAL_BOOTSTRAP_BODIES',definitions)
                cpp,binary=work/('bootstrap-'+str(version)+'-'+feature+'.cc'),work/('bootstrap-'+str(version)+'-'+feature)
                cpp.write_text(fixture)
                command=[os.environ.get('CXX','c++'),'-std=c++14','-O2','-Wall','-Wextra','-Werror',*flags,
                    '-DPHP_VERSION_ID='+str(version),'-I'+str(ROOT/'native/phpcoroutines'),str(cpp),'-o',str(binary)]
                if feature=='selected': command+=['-DSWOOLE_RS_PHPCOROUTINES=1',str(archive),'-lpthread','-ldl','-lm']
                run(command)
                result=run([str(binary)])
                outputs.append(result.stdout)
            if outputs[0]!=outputs[1]: raise ValueError('Native and selected MINIT metadata/effect traces differ')
        report['bootstrap']['matched']=True
        from transfer_bodies import SIGNATURES as transfer_signatures
        report['transfer'] = dict(exact_bodies=8, ordinary_configurations_per_capability=32, stack_limit_capabilities=[False, True],
            actual_zend_vm_output_allocator_or_callbacks=False, native_lifecycle=False)
        for stack_limit in (False, True):
            outputs = []
            for feature, source in [('native', coroutine_original), ('selected', coroutine_selected)]:
                definitions = '\n'.join(signature + body(source, signature) + '}' for signature in transfer_signatures)
                fixture = (ROOT / 'tests/modules/phpcoroutines/transfer.cc').read_text().replace('// ACTUAL_TRANSFER_BODIES', definitions)
                if feature == 'selected':
                    selected_header = header_selected((args.source / HEADER_DEST).read_text())
                    signature = 'static inline swr_phpcoroutines_context_cells php_coroutine_metadata_cells(PHPContext *ctx) {'
                    fixture = fixture.replace('// ACTUAL_METADATA_HELPER', signature + body(selected_header, signature) + '}')
                cpp, binary = work / ('transfer-' + str(int(stack_limit)) + '-' + feature + '.cc'), work / ('transfer-' + str(int(stack_limit)) + '-' + feature)
                cpp.write_text(fixture)
                command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                    '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
                if stack_limit: command += ['-DZEND_CHECK_STACK_LIMIT=1']
                if feature == 'selected': command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
                run(command)
                result = run([str(binary)])
                outputs.append(result.stdout)
            if outputs[0] != outputs[1]: raise ValueError('Native and selected context-transfer traces differ')
        report['transfer']['matched'] = True
        from config_bodies import CONFIG_SIGNATURES, CONFIG_DECL, CONFIG_SELECTED_DECL
        report['config_state'] = dict(exact_header_bodies=5, native_scope_modes=['global', 'thread_local'],
            dynamic_initializer_or_allocation=False, actual_zend_hook_thread_or_lifecycle=False)
        header_original = (args.source / HEADER_DEST).read_text()
        header_overlay = header_selected(header_original)
        public_config = '    struct Config {' + body(header_original, 'struct Config {') + '};'
        for tls in (False, True):
            outputs = []
            for feature, header_source, cpp_source in [('native', header_original, coroutine_original), ('selected', header_overlay, coroutine_selected)]:
                definitions = '\n'.join(signature + body(header_source, signature) + '}' for signature in CONFIG_SIGNATURES)
                if feature == 'native':
                    start = cpp_source.index('SW_THREAD_LOCAL PHPCoroutine::Config PHPCoroutine::config{')
                    seed = cpp_source[start:cpp_source.index('};', start) + 2]
                else:
                    start = cpp_source.index('#ifdef SWOOLE_RS_PHPCOROUTINES\nSW_THREAD_LOCAL swr_phpcoroutines_config_state PHPCoroutine::config{')
                    seed = cpp_source[start:cpp_source.index('#endif', start) + len('#endif')]
                fixture = (ROOT / 'tests/modules/phpcoroutines/config.cc').read_text().replace('// ACTUAL_PUBLIC_CONFIG', public_config).replace('// ACTUAL_CONFIG_DECL', CONFIG_DECL if feature == 'native' else CONFIG_SELECTED_DECL).replace('// ACTUAL_CONFIG_HEADER_BODIES', definitions).replace('// ACTUAL_CONFIG_SEED', seed)
                cpp, binary = work / ('config-' + str(int(tls)) + '-' + feature + '.cc'), work / ('config-' + str(int(tls)) + '-' + feature)
                cpp.write_text(fixture)
                command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                    '-DCONFIG_THREAD_LOCAL=' + str(int(tls)), '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary), '-lpthread']
                if feature == 'selected': command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-ldl', '-lm']
                run(command)
                result = run([str(binary)])
                outputs.append(result.stdout)
            if outputs[0] != outputs[1]: raise ValueError('Native and selected config state/custody differ')
        report['config_state']['matched'] = True
        policy_source = ROOT / 'tests/modules/phpcoroutines/autoload-policy.cc'
        policy_binary = work / 'autoload-policy'
        run([os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
             '-I' + str(ROOT / 'native/phpcoroutines'), str(policy_source), str(archive),
             '-lpthread', '-ldl', '-lm', '-o', str(policy_binary)])
        result = run([str(policy_binary)])
        report['autoload_policy_facts'] = dict(stdout=result.stdout, scalar_routes=5, native_autoload_execution=False,
            classloader_context_callbacks=False, whole_body_execution=False)
        report['autoload_metadata_models'] = dict(fifo_records=4096, native_control='std::queue<uintptr_t>', actual_autoload_execution=False)
        header = (args.source / HEADER_DEST).read_text()
        report['header_context'] = dict(bodies=len(HEADER_SIGNATURES),
            limits=['Inert native getter/clock/page controls; no actual Zend VM/Coroutine/clock effects.',
                    'Native missing-context error, concurrency, lifetime and signed-overflow domains unexecuted.'])
        context_outputs = []
        for feature, source in [('native', header), ('selected', header_selected(header))]:
            definitions = '\n'.join(signature + body(source, signature) + '}' for signature in HEADER_SIGNATURES)
            fixture = (ROOT / 'tests/modules/phpcoroutines/context.cc').read_text().replace('// ACTUAL_HEADER_BODIES', definitions)
            if feature == 'selected':
                signature = 'static inline swr_phpcoroutines_context_cells php_coroutine_metadata_cells(PHPContext *ctx) {'
                fixture = fixture.replace('// ACTUAL_METADATA_HELPER', signature + body(source, signature) + '}')
            cpp, binary = work / ('context-' + feature + '.cc'), work / ('context-' + feature)
            cpp.write_text(fixture)
            command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
                       '-I' + str(ROOT / 'native/phpcoroutines'), str(cpp), '-o', str(binary)]
            if feature == 'selected':
                command += ['-DSWOOLE_RS_PHPCOROUTINES=1', str(archive), '-lpthread', '-ldl', '-lm']
            run(command)
            result = run([str(binary)])
            context_outputs.append(result.stdout)
        if context_outputs[0] != context_outputs[1]:
            raise ValueError('Native and selected common-header query/stack/scheduler traces differ')
        report['header_context']['matched'] = True
        if any(sha(ROOT / path) != digest for path, digest in report['rust_sources_sha256'].items()):
            raise ValueError('Module source changed during matched controls')
        if sha(archive) != report['archive_sha256']:
            raise ValueError('Archive changed during matched controls')
        report.update(passed=True, matched_traces=True, tasks=6, create_stub_calls=6, pure_queue_order_cases=4096,
                      pure_queue_max_count=True, native_task_execution=False)
    except Exception as error:
        report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'error', 'work')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
