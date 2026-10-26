#!/usr/bin/env python3
"""Short, explicit edit/candidate/integration loops with durable phase timings."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.harness import ROOT, write_report
from tools.build_hybrid import GRADUATED, MODULES, SELECTABLE, profile_suffix, build_alias
from tools.build_upstream import require_build_space
from tools.dev_report import read_json
from tools.private_copy import copy_private


# Exit 0 only when this Python can configure a TLS 1.3-only client context.
TLS13_PROBE = """import ssl, sys
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
try:
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
except ValueError:
    sys.exit(2)
sys.exit(0 if ssl.HAS_TLSv1_3 else 2)"""


def require_frozen_source(expected):
    """Boundary guard; individual build/source/artifact attestations remain required."""
    def head():
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    observed = head()
    if observed != expected:
        raise ValueError('Frozen source HEAD changed: expected ' + expected + ', observed ' + observed)
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True)
    if dirty.strip() or head() != expected:
        raise ValueError('Frozen source checkout changed; preserve the run and use a clean immutable checkout')


# A change here can affect every module's native build or behaviour.
SHARED_PATHS = ('crates/ffi/', 'native/include/', 'native/integration/', 'native/halfclose/',
                'migration/patches/integration/', 'migration/patches/halfclose/', 'Cargo.toml', 'Cargo.lock',
                'tools/build_hybrid.py', 'tools/build_upstream.py', 'migration/modules.json')


def changed_modules(base):
    """Modules whose owned paths the diff from BASE touches; shared build inputs select every module."""
    names = {module_id: name for name, (module_id, _) in MODULES.items()}
    owners = [(path, names.get(module['id'])) for module in json.loads((ROOT / 'migration/modules.json').read_text())['modules']
              for path in module['owned_paths']]
    selected = set()
    for path in subprocess.check_output(['git', 'diff', '--name-only', base + '...HEAD'], cwd=ROOT, text=True).split():
        owner = next((name for owned, name in owners if name and (path == owned or path.startswith(owned))), None)
        if owner:
            selected.add(owner)
        elif path.startswith(SHARED_PATHS):
            return sorted(MODULES)
    return sorted(selected)


def selected_modules(args):
    chosen = MODULES if getattr(args, 'all_modules', False) else args.module or ['buffer', 'websocket']
    return sorted(set(chosen) | set(GRADUATED))


def typed_buffer(args):
    """Configure enables the typed Buffer queue whenever both Rust Buffer and Rust reactor are built."""
    return {'buffer', 'reactor'} <= set(selected_modules(args))


def build_variant(args):
    suffix = ('-halfclose' if getattr(args, 'fix_halfclose', False) else '') + profile_suffix(args)
    return build_alias('rust', selected_modules(args), suffix, dev=args.lane != 'integrate')


def verify_artifact_report(args):
    """Reuse completed bytes, never earlier test outcomes or another source cohort."""
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    identities = {}
    for label, variant in [('selected', build_variant(args)),
                           ('native', build_alias('upstream', [], profile_suffix(args)))]:
        folder = args.artifacts_from / (label + '-export')
        receipt = json.loads((folder / 'export.json').read_text())
        if receipt['source_ref'] != source:
            raise ValueError('Artifact source differs: ' + label)
        for name, identity in receipt['files'].items():
            if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != identity['sha256']:
                raise ValueError('Export file changed: ' + label + '/' + name)
        manifest = json.loads((folder / 'build-manifest.json').read_text())
        origins = [receipt.get('producer_source_ref'), manifest.get('producer_source_ref')]
        if any(origin is not None for origin in origins) and any(origin != receipt['source_ref'] for origin in origins):
            raise ValueError('Artifact producer source differs: ' + label)
        if (manifest['build_mode'] != 'immutable'
                or ('--enable-swoole-stdext' in manifest['configure']) != args.stdext
                or manifest['inputs'].get('php_sockets_requested', False) != getattr(args, 'php_sockets', False)
                or ('--enable-sockets' in manifest['configure']) != getattr(args, 'php_sockets', False)
                or label == 'selected' and (sorted(set(manifest['inputs']['modules']) | set(GRADUATED)) != selected_modules(args)
                    or manifest['inputs']['fix_halfclose'] != args.fix_halfclose)):
            raise ValueError('Artifact configuration differs: ' + label)
        build = ROOT / 'target/hybrid' / variant
        for name, path in [('swoole.so', build / 'modules/swoole.so'),
                           ('build-manifest.json', build / 'build-manifest.json')]:
            if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['files'][name]['sha256']:
                raise ValueError('Current build alias differs: ' + label + '/' + name)
        identities[label] = {'path': str(folder), 'export_sha256': hashlib.sha256((folder / 'export.json').read_bytes()).hexdigest()}
    return identities


def plan(args, reports):
    modules = selected_modules(args)
    python = sys.executable
    commands = []
    def add(name, *command):
        commands.append((name, list(map(str, command))))
    def script(name, path, *options):
        child = ['--match-child-php'] if getattr(args, 'match_child_php', False) and path == 'corpus/upstream/run.py' else []
        add(name, python, path, *options, *child)
    def report(name):
        return ['--output', str(reports / (name + '.json'))]
    def pytest(name, path, *options):
        add(name, python, '-m', 'pytest', '-q', path, *options, '--junitxml', str(reports / (name + '.xml')))
    php = ['--php', args.php]
    for extension in args.php_extension:
        php += ['--php-extension', extension]
    def php_for(*dependencies):
        return php + [argument for extension in dependencies
                      if sys.platform.startswith('linux') and extension not in args.php_extension
                      for argument in ['--php-extension', extension]]
    flags = [arg for module in modules if module not in GRADUATED for arg in ['--module', module]]
    for module in modules:
        add(module + '-unit', 'cargo', 'test', '--locked', '-p', 'swoole-rs-' + module,
            *([args.test] if args.test and args.lane == 'edit' else []))
    if args.lane == 'edit':
        return commands
    integrate = args.lane == 'integrate'
    repair = ['--fix-halfclose'] if getattr(args, 'fix_halfclose', False) else []
    variant = build_variant(args)
    manifest = ROOT / 'target/hybrid' / variant / 'build-manifest.json'
    hybrid = manifest.parent / 'modules/swoole.so'
    captured_reference = integrate and (getattr(args, 'php_sockets', False) or bool({'buffer', 'utilities', 'ports', 'phphelpers', 'phpevents', 'reactor', 'phpcoroutines', 'coroutine'} & set(modules)) or {'http', 'corebase'} <= set(modules))
    native_variant = build_alias('upstream', [], profile_suffix(args))
    reference = (ROOT / 'target/hybrid' / native_variant / 'modules/swoole.so'
                 if captured_reference or getattr(args, 'stdext', False) or getattr(args, 'php_sockets', False) else ROOT / 'target/upstream/src/modules/swoole.so')
    engines = ['--engine', f'hybrid={hybrid}']
    if integrate or args.compare or args.benchmark:
        engines += ['--engine', f'upstream={reference}']
    if integrate:
        pytest('timer-model', 'tests/modules/timer/test_model.py')
        pytest('timer-kernel', 'tests/modules/timer/test_kernel.py', '--sanitize')
        add('format', 'cargo', 'fmt', '--all', '--check')
        add('clippy', 'cargo', 'clippy', '--locked', '--workspace', '--all-targets', '--all-features', '--', '-D', 'warnings')
    script('ownership', 'tools/check_migration.py')
    artifact_reports = getattr(args, 'artifacts_from', None) or reports
    native_export = artifact_reports / 'native-export'
    if getattr(args, 'stdext', False) or getattr(args, 'php_sockets', False) or captured_reference:
        script('stdext-reference-build' if getattr(args, 'stdext', False) else 'reference-build',
               'tools/build_hybrid.py', '--backend', 'upstream',
               *(['--stdext'] if getattr(args, 'stdext', False) else []),
               *(['--php-sockets'] if getattr(args, 'php_sockets', False) else []), '--jobs', args.jobs,
               *(['--export', native_export] if captured_reference else []),
               *(['--ccache', args.ccache] if getattr(args, 'ccache', None) else ['--no-ccache']),
               *(['--native-build-root', args.native_build_root] if getattr(args, 'native_build_root', None) else []))
    selected_export = artifact_reports / 'selected-export'
    script('build', 'tools/build_hybrid.py', *([] if integrate else ['--dev']), *flags, *repair, *(['--stdext'] if getattr(args, 'stdext', False) else []), *(['--php-sockets'] if getattr(args, 'php_sockets', False) else []),
           *(['--export', selected_export] if captured_reference else []), '--jobs', args.jobs,
           *(['--native-build-root', args.native_build_root] if getattr(args, 'native_build_root', None) else []),
           *(['--ccache', args.ccache] if getattr(args, 'ccache', None) else ['--no-ccache']))
    script('abi', 'tests/modules/integration/test_bridge.py', *php_for('sockets'), '--hybrid', hybrid, '--reference', reference,
           *([] if integrate else ['--startup-only']))
    if integrate:
        script('abi-startup', 'tests/modules/integration/test_bridge.py', *php_for('sockets'), '--hybrid', hybrid,
               '--reference', reference, '--startup-only')
        script('api-surface', 'tools/capability_inventory.py', '--source', ROOT / 'target/upstream/src',
               *php_for('curl', 'sockets', 'tokenizer'), *engines, '--require-same-api', *report('api-surface'))
    if integrate and {'base64', 'crc32'} & set(modules):
        reference_identity = reports / 'reference-identity.json'
        script('reference-identity', 'tools/extension_identity.py', '--source', ROOT / 'target/upstream/src',
               '--extension', reference, *php, '--output', reference_identity)
        for module, runner in [('base64', 'consumers.py'), ('crc32', 'consumer.py')]:
            if module in modules:
                consumer_php = php_for('curl') if module == 'base64' else php
                for label, extension, identity in [('upstream', reference, reference_identity),
                                                    ('hybrid', hybrid, manifest)]:
                    name = module + '-consumers-' + label
                    script(name, 'tests/modules/' + module + '/' + runner, '--extension', extension,
                           '--manifest', identity, *consumer_php, *report(name))
    if 'error' in modules:
        script('error-native', 'tools/core_check.py', '--module', 'error',
               '--build-manifest', manifest, '--sanitize', *report('error-native'))
    if 'error' in modules and integrate:
        script('error-php', 'tests/modules/error/php.py', '--source', ROOT / 'target/upstream/src',
               *php, *engines, *report('error-php'))
    if integrate and {'http', 'corebase'} <= set(modules):
        script('http-boundary-rng', 'tests/modules/http/boundary_rng_gate.py',
               '--source', ROOT / 'target/upstream/src', '--export', selected_export, *report('http-boundary-rng'))
    if 'http' in modules:
        script('http-context', 'tests/modules/http/context_gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('http-context'))
        for name, runner in [('http-native', 'gate.py'), ('http-ranges', 'range_gate.py'), ('http-framing', 'framing_gate.py'), ('http-headers', 'headers_gate.py'), ('http-proxy', 'proxy_gate.py'), ('http-static', 'static_gate.py'), ('http-paths', 'path_gate.py'), ('http-index-pages', 'index_page_gate.py'), ('http-conditionals', 'conditional_gate.py'), ('http-multipart', 'multipart_gate.py'), ('http-rewrites', 'rewrite_gate.py'), ('http-inline', 'inline_gate.py'), ('http-dispatch', 'dispatch_gate.py'), ('http-multipart-emit', 'multipart_emit_gate.py'), ('http-locales', 'locale_gate.py')]:
            script(name, 'tests/modules/http/' + runner, '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report(name))
        script('http-index-append-positive', 'tests/modules/http/index_page_gate.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--positive-only', *report('http-index-append-positive'))
        script('http-url-encode-positive', 'tests/modules/http/gate.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--url-positive-only', *report('http-url-encode-positive'))
        script('http-proxy-auth-positive', 'tests/modules/http/proxy_gate.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--auth-positive-only', *report('http-proxy-auth-positive'))
        for name, runner in [('static', 'static_gate.py'), ('rewrites', 'rewrite_gate.py')]:
            phase = 'http-' + name + '-positive'
            script(phase, 'tests/modules/http/' + runner, '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--positive-only',
                   *report(phase))
        for phase, flags in [('http-cookie-flow-positive', []), ('http-status-buffer-positive', ['--status-only']), ('http-status-codes-positive', ['--codes-only'])]:
            script(phase, 'tests/modules/http/cookie_flow_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *flags, *report(phase))
        script('http-multipart-headers-positive', 'tests/modules/http/multipart_headers_gate.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--positive-only', *report('http-multipart-headers-positive'))
        script('http-request-lifecycle', 'tests/modules/http/request_lifecycle_gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('http-request-lifecycle'))
        script('http-directory-compatibility', 'tests/modules/http/directory_compat.py', '--source', ROOT / 'target/upstream/src',
               *report('http-directory-compatibility'))
    if 'locks' in modules:
        script('locks-native', 'tests/modules/locks/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *report('locks-native'))
    if 'wrappers' in modules:
        script('wrappers-native', 'tests/modules/wrappers/gate.py', '--archive',
               manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *report('wrappers-native'))
        wrapper_includes = (['--include', str(Path(subprocess.check_output(['brew', '--prefix', 'openssl@3'], text=True).strip()) / 'include')]
                            if sys.platform == 'darwin' else [])
        for consumer in ['listener', 'response']:
            name = 'wrappers-' + consumer
            script(name, 'tests/modules/wrappers/' + consumer + '.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--core', manifest.parent / 'src',
                   '--sanitize', *wrapper_includes, *report(name))
    if 'reactor' in modules:
        if integrate:
            for phase, extra in [('reactor-production-supported', []), ('reactor-production-callbacks', ['--callbacks']),
                                 ('reactor-production-handlers', ['--handlers']), ('reactor-production-builtins', ['--builtins']),
                                 ('reactor-production-socket-output', ['--socket-output', '--require-output-workflow']),
                                 ('reactor-production-blocking', ['--blocking']), ('reactor-production-ordinary-io', ['--ordinary-io']), ('reactor-production-datagram', ['--datagram']),
                                 ('reactor-production-owned-iov', ['--blocking', '--require-owned-iov']),
                                 ('reactor-production-owned-defer', ['--builtins', '--require-owned-defer'])]:
                script(phase, 'tests/modules/reactor/production_supported.py',
                       '--source', ROOT / 'target/upstream/src', '--source-ref', 'HEAD', *php_for(),
                       '--engine', f'hybrid={selected_export / "swoole.so"}',
                       '--engine', f'upstream={native_export / "swoole.so"}', '--build-manifest', manifest,
                       '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                       '--selected-export', selected_export / 'export.json', '--native-export', native_export / 'export.json',
                       '--require-batch', *(['--require-typed-buffer'] if typed_buffer(args) else []),
                       *extra, *report(phase))
        for name in ['registration', 'write_positive', 'write_arguments', 'output', 'wait', 'callbacks', 'initialize', 'handlers', 'builtins']:
            phase = 'reactor-' + name.replace('_', '-')
            script(phase, 'tests/modules/reactor/' + name + '.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
                   '--report', reports / (phase + '.json'))
        script('reactor-callback-queues', 'tests/modules/reactor/callback_queues.py',
               '--source', ROOT / 'target/upstream/src', '--sanitize',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--report', reports / 'reactor-callback-queues.json')
        script('reactor-write-workflow', 'tests/modules/reactor/write_positive.py',
               '--source', ROOT / 'target/upstream/src', '--workflow', '--sanitize',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--report', reports / 'reactor-write-workflow.json')
        for phase, flag in [('reactor-blocking-output', '--blocking'), ('reactor-iov-progress', '--iov-progress'), ('reactor-ordinary-io', '--ordinary-io'), ('reactor-socket-policy', '--socket-policy'), ('reactor-fd-options', '--fd-options'), ('reactor-socket-options', '--socket-options'), ('reactor-forwarding', '--forwarding'), ('reactor-datagram', '--datagram'), ('reactor-connect', '--connect')]:
            script(phase, 'tests/modules/reactor/output.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', flag,
                   '--report', reports / (phase + '.json'))
        script('reactor-batch', 'tests/modules/reactor/batch.py',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'reactor-batch.json')
        script('reactor-backend-storage', 'tests/modules/reactor/backend_storage.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'reactor-backend-storage.json')
        script('reactor-flush', 'tests/modules/reactor/flush.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'reactor-flush.json')
        script('reactor-poll-snapshot', 'tests/modules/reactor/poll_snapshot.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'reactor-poll-snapshot.json')
        script('reactor-ordered', 'tests/modules/reactor/ordered_gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'reactor-ordered.json')
        script('reactor-filters', 'tests/modules/reactor/filters_gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'reactor-filters.json')
        script('reactor-compile', 'tests/modules/reactor/compile_gate.py', '--source', ROOT / 'target/upstream/src',
               '--report', reports / 'reactor-compile.json')
    if typed_buffer(args):
        pytest('buffer-typed-layout', 'tests/modules/buffer/test_typed_layout.py')
        pytest('buffer-typed', 'tests/modules/buffer/test_typed.py', '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize')
        script('reactor-buffer-typed-compile', 'tests/modules/reactor/buffer_typed_compile.py',
               '--source', ROOT / 'target/upstream/src',
               '--master-patch', ROOT / 'migration/patches/integration/0003-server-static-config.patch',
               '--report', reports / 'reactor-buffer-typed-compile.json')
    if 'coroutine' in modules:
        if integrate:
            script('coroutine-production-stack', 'tests/modules/coroutine/production_stack.py',
                   '--source', ROOT / 'target/upstream/src', '--source-ref', 'HEAD', *php,
                   '--selected-export', selected_export / 'export.json',
                   '--native-export', native_export / 'export.json', *report('coroutine-production-stack'))
        for name in ['tokens', 'stack', 'timing', 'scheduler']:
            phase = 'coroutine-' + name
            script(phase, 'tests/modules/coroutine/' + name + '.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
                   '--report', reports / (phase + '.json'))
        script('coroutine-registry-metadata', 'tests/modules/coroutine/registry.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'coroutine-registry-metadata.json')
        script('coroutine-registry-order', 'tests/modules/coroutine/registry_order.py',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--native-sanitize', '--report', reports / 'coroutine-registry-order.json')
        for backend in ['ucontext', 'asm', 'thread']:
            phase = 'coroutine-registry-compile' + ('' if backend == 'ucontext' else '-' + backend)
            script(phase, 'tests/modules/coroutine/compile_gate.py',
                   '--source', ROOT / 'target/upstream/src', '--registry', '--timing', '--stack-usage',
                   '--backend', backend, '--report', reports / (phase + '.json'))
        if integrate and 'phpcoroutines' in modules:
            script('coroutine-registry-sdk', 'tests/modules/coroutine/registry_sdk.py',
                   '--source', ROOT / 'target/upstream/src',
                   '--sdk-export', selected_export / 'export.json',
                   '--report', reports / 'coroutine-registry-sdk.json')
        script('coroutine-channel-state', 'tests/modules/coroutine/channel_state_gate.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--report', reports / 'coroutine-channel-state.json')
        if integrate:
            script('coroutine-channel-state-sdk', 'tests/modules/coroutine/channel_state_sdk.py',
                   '--source', ROOT / 'target/upstream/src',
                   '--sdk-export', selected_export / 'export.json',
                   '--native-export', native_export / 'export.json',
                   '--report', reports / 'coroutine-channel-state-sdk.json')
        script('coroutine-ordered', 'tests/modules/coroutine/ordered_gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               '--report', reports / 'coroutine-ordered.json')
        script('coroutine-compile', 'tests/modules/coroutine/compile_gate.py', '--source', ROOT / 'target/upstream/src',
               '--report', reports / 'coroutine-compile.json')
        script('coroutine-stack-compile', 'tests/modules/coroutine/compile_gate.py',
               '--source', ROOT / 'target/upstream/src', '--stack-usage',
               '--report', reports / 'coroutine-stack-compile.json')
        script('coroutine-timing-compile', 'tests/modules/coroutine/compile_gate.py',
               '--source', ROOT / 'target/upstream/src', '--timing', '--stack-usage',
               '--report', reports / 'coroutine-timing-compile.json')
    if 'hooks' in modules:
        for name, runner in [('hooks-ordered', 'ordered_gate.py'), ('hooks-async-policy', 'async_gate.py'),
                             ('hooks-packet-policy', 'packet_gate.py'), ('hooks-socket-policy', 'socket_policy_gate.py'),
                             ('hooks-lifecycle-policy', 'lifecycle_gate.py')]:
            script(name, 'tests/modules/hooks/' + runner, '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
                   '--report', reports / (name + '.json'))
        script('hooks-compile', 'tests/modules/hooks/compile_gate.py', '--source', ROOT / 'target/upstream/src',
               '--config', manifest.parent / 'src/config.h', '--report', reports / 'hooks-compile.json')
    if 'httpbindings' in modules:
        for family in ['cookie', 'server']:
            name = 'httpbindings-' + family
            script(name, 'tests/modules/httpbindings/' + family + '_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report(name))
        for suffix, options in [('', []), ('-without-compression', ['--without-compression'])]:
            name = 'httpbindings-request' + suffix
            script(name, 'tests/modules/httpbindings/request_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *options, *report(name))
        for capabilities in range(8):
            name = 'httpbindings-payload-' + str(capabilities)
            script(name, 'tests/modules/httpbindings/payload_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--capabilities', capabilities, *report(name))
        for locale in ['C', 'C.UTF-8', 'en_US.ISO8859-1', 'tr_TR.ISO8859-9', 'tr_TR.UTF-8']:
            name = 'httpbindings-libc-' + locale
            script(name, 'tests/modules/httpbindings/payload_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--native-libc', '--locale', locale, *report(name))
        for suffix, options in [('', []), ('-without-compression', ['--without-compression'])]:
            name = 'httpbindings-response' + suffix
            script(name, 'tests/modules/httpbindings/response_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *options, *report(name))
        for locale in ['C', 'C.UTF-8', 'en_US.ISO8859-1', 'tr_TR.ISO8859-9', 'tr_TR.UTF-8']:
            name = 'httpbindings-response-libc-' + locale
            script(name, 'tests/modules/httpbindings/response_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--native-libc', '--locale', locale, *report(name))
        for suffix, options in [('', []), ('-without-compression', ['--without-compression'])]:
            name = 'httpbindings-settings' + suffix
            script(name, 'tests/modules/httpbindings/settings_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *options, *report(name))
        for family, profiles in [
            ('emission', [('', []), ('-without-zlib', ['--without-zlib']),
                          ('-without-compression', ['--without-compression'])]),
            ('file', [('', []), ('-without-compression', ['--without-compression'])]),
        ]:
            for suffix, options in profiles:
                name = 'httpbindings-' + family + suffix
                script(name, 'tests/modules/httpbindings/' + family + '_gate.py',
                       '--source', ROOT / 'target/upstream/src',
                       '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                       *options, *report(name))
        for capabilities in range(8):
            name = 'httpbindings-codec-' + str(capabilities)
            script(name, 'tests/modules/httpbindings/codec_gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--capabilities', capabilities, *report(name))
        if integrate:
            source_ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            script('httpbindings-php', 'tests/modules/httpbindings/php_gate.py', '--source-ref', source_ref,
                   '--build-manifest', 'hybrid=' + str(manifest),
                   '--archive', 'hybrid=' + str(manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a'),
                   *php, '--engine', f'upstream={reference}',
                   '--engine', f'hybrid={hybrid}', *report('httpbindings-php'))
    if 'http2' in modules:
        includes = (['--include', str(Path(subprocess.check_output(['brew', '--prefix', 'openssl@3'], text=True).strip()) / 'include')]
                    if sys.platform == 'darwin' else [])
        script('http2-native', 'tests/modules/http2/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *includes, *report('http2-native'))
        for family, runner in [('settings', 'settings_calls.py'), ('control', 'control_calls.py'), ('header', 'header_calls.py'),
                               ('queue', 'queue_calls.py'), ('window', 'window_calls.py'),
                               ('response-headers', 'response_headers.py'), ('publication', 'publication_calls.py'),
                               ('write', 'write_calls.py'), ('send', 'send_calls.py'),
                               ('server-header', 'server_header_calls.py'), ('request-headers', 'request_headers.py'), ('response-builders', 'response_builders.py'), ('response-lifecycle', 'response_lifecycle.py'), ('connection', 'connection_calls.py'), ('file', 'file_calls.py'), ('receive', 'receive_calls.py'),
                               ('syntax', 'syntax_gate.py')]:
            name = 'http2-' + family
            script(name, 'tests/modules/http2/' + runner, '--source', ROOT / 'target/upstream/src',
                   '--core-report', reports / 'http2-native.json', *includes, *report(name))
    if 'clients' in modules:
        for name, runner in [('clients-policy', 'gate.py'), ('clients-http', 'http_gate.py'), ('clients-codec', 'codec_gate.py'),
                             ('clients-lifecycle', 'lifecycle_gate.py'), ('clients-write', 'write_gate.py'), ('clients-read', 'read_gate.py'),
                             ('clients-connect', 'connect_gate.py'), ('clients-persistent', 'persistent_gate.py'),
                             ('clients-resolver-config', 'resolv_gate.py'), ('clients-transport', 'transport_gate.py'),
                             ('clients-pool', 'pool_gate.py'), ('clients-resolver', 'resolver_gate.py'),
                             ('clients-http-connection', 'http_connection_gate.py'), ('clients-http-response', 'http_response_gate.py'), ('clients-http-format', 'http_format_gate.py'), ('clients-coro', 'coro_gate.py'), ('clients-async', 'async_gate.py'), ('clients-object', 'object_gate.py'),
                             ('clients-ip', 'ip_gate.py'), ('clients-ip-text', 'ip_text_gate.py'), ('clients-coro-io', 'coro_io_gate.py')]:
            script(name, 'tests/modules/clients/' + runner, '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *report(name))
        if integrate:
            for family in ['http', 'dns', 'lifecycle', 'pool', 'resolver', 'pool_fork', 'http_connection', 'http_format', 'coro', 'async', 'coro_io']:
                name = 'clients-php-' + family
                script(name, 'tests/modules/clients/php_' + family + '.py', '--build-manifest', manifest,
                       *(['--source-ref', 'HEAD'] if family != 'lifecycle' else []),
                       *php_for('curl', 'sockets'), *engines, *report(name))
    if 'phpcollections' in modules:
        script('phpcollections-policy', 'tests/modules/phpcollections/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('phpcollections-policy'))
        if integrate:
            script('phpcollections-runtime', 'tests/modules/phpcollections/php_runtime.py', *php_for('curl'), *engines,
                   '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', 'HEAD', *report('phpcollections-runtime'))
            script('phpcollections-column-bytes', 'tests/modules/phpcollections/php_runtime.py', *php_for('curl'), *engines,
                   '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', 'HEAD', '--profile', 'column-bytes', *report('phpcollections-column-bytes'))
            script('phpcollections-global-handlers', 'tests/modules/phpcollections/handlers.py',
                   '--source', ROOT / 'target/upstream/src', '--source-ref', 'HEAD',
                   *php, *engines, '--build-manifest', manifest,
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   *report('phpcollections-global-handlers'))
            if getattr(args, 'redis_extension', None):
                script('phpcollections-prerequisites', 'tests/modules/phpcollections/originals.py',
                       '--source', ROOT / 'target/upstream/src', '--source-ref', 'HEAD',
                       '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                       *php_for('curl', 'sockets', 'posix', 'mbstring', 'igbinary'), *engines,
                       '--redis-extension', args.redis_extension,
                       *(['--redis-image', args.redis_image] if getattr(args, 'redis_image', None) else []),
                       *report('phpcollections-prerequisites'))
    if 'phphelpers' in modules:
        script('phphelpers-async', 'tests/modules/phphelpers/async_gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('phphelpers-async'))
        script('phphelpers-policy', 'tests/modules/phphelpers/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('phphelpers-policy'))
        if integrate:
            script('phphelpers-sdk', 'tests/modules/phphelpers/sdk.py', '--source', ROOT / 'target/upstream/src',
                   '--sdk-export', selected_export / 'export.json', *report('phphelpers-sdk'))
            for provider in ['sqlite', 'odbc']:
                phase = 'phphelpers-async-' + provider + '-sdk'
                script(phase, 'tests/modules/phphelpers/async_optional_sdk.py', '--source', ROOT / 'target/upstream/src',
                       '--sdk-report', reports / 'phphelpers-sdk.json', '--provider', provider, *report(phase))
            script('phphelpers-facade-runtime', 'tests/modules/phphelpers/facade_runtime.py',
                   '--sdk-report', reports / 'phphelpers-sdk.json', *php_for('curl'), *engines,
                   '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', 'HEAD', *report('phphelpers-facade-runtime'))
            script('phphelpers-entrypoint', 'tests/modules/phphelpers/entrypoint.py',
                   '--sdk-report', reports / 'phphelpers-sdk.json', *php_for('curl'), *engines,
                   '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', 'HEAD', *report('phphelpers-entrypoint'))
            script('phphelpers-runtime', 'tests/modules/phphelpers/runtime.py', *php, *engines,
                   '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', 'HEAD', *report('phphelpers-runtime'))
    if 'phpevents' in modules:
        script('phpevents-policy', 'tests/modules/phpevents/gate.py', '--source', ROOT / 'target/upstream/src',
               '--sanitize', *report('phpevents-policy'))
        if integrate:
            script('phpevents-sdk', 'tests/modules/phpevents/sdk.py', '--source', ROOT / 'target/upstream/src',
                   '--sdk-export', selected_export / 'export.json', '--native-export', native_export,
                   *report('phpevents-sdk'))
        if integrate and 'phphelpers' in modules:
            script('phpevents-descriptors', 'tests/modules/phpevents/descriptor_runtime.py',
                   '--sdk-report', reports / 'phphelpers-sdk.json', *php_for('curl'), *engines,
                   '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', 'HEAD', *report('phpevents-descriptors'))
    if 'phpcoroutines' in modules:
        for suffix, options in [('', []), ('-native-sanitized', ['--sanitize'])]:
            name = 'phpcoroutines-method-catalogue' + suffix
            script(name, 'tests/modules/phpcoroutines/methods.py',
                   '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   *options, *report(name))
        script('phpcoroutines-ffi', 'tests/modules/phpcoroutines/ffi.py',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('phpcoroutines-ffi'))
        script('phpcoroutines-context-metadata', 'tests/modules/phpcoroutines/context_metadata.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               *report('phpcoroutines-context-metadata'))
        script('phpcoroutines-join-metadata', 'tests/modules/phpcoroutines/join_metadata.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               *report('phpcoroutines-join-metadata'))
        script('phpcoroutines-policy', 'tests/modules/phpcoroutines/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *report('phpcoroutines-policy'))
        if integrate and 'phphelpers' in modules:
            script('phpcoroutines-sdk', 'tests/modules/phpcoroutines/sdk.py', '--source', ROOT / 'target/upstream/src',
                   '--sdk-report', reports / 'phphelpers-sdk.json', *report('phpcoroutines-sdk'))
        if integrate:
            script('phpcoroutines-statistics', 'tests/modules/integration/php_statistics.py', *php,
                   '--engine', f'hybrid={selected_export / "swoole.so"}',
                   '--engine', f'upstream={native_export / "swoole.so"}',
                   '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', 'HEAD',
                   '--selected-export', selected_export / 'export.json', '--native-export', native_export / 'export.json',
                   *report('phpcoroutines-statistics'))
        if integrate:
            for suffix, profile in [('idle-queries', 'idle-queries'), ('frontend-statistics', 'statistics'), ('startup', 'startup'), ('configuration', 'configuration')]:
                phase = 'phpcoroutines-' + suffix
                script(phase, 'tests/modules/phpcoroutines/stats_runtime.py',
                       '--profile', profile, *php_for('curl'), *engines, '--build-manifest', manifest,
                       '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                       '--source-ref', 'HEAD', *report(phase))
    if 'ports' in modules:
        if integrate:
            for name, runner in [('ports-php', 'server.py'), ('ports-configuration', 'configuration.py'),
                                 ('ports-callback-php', 'callback_php.py')]:
                script(name, 'tests/modules/ports/' + runner, *php_for('curl', 'sockets'), *engines,
                       '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                       '--source-ref', 'HEAD', *report(name))
        script('ports-socket', 'tests/modules/ports/socket_workflow.py', '--source', ROOT / 'target/upstream/src',
               '--core', manifest.parent / 'src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('ports-socket'))
        script('ports-listen', 'tests/modules/ports/listen.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('ports-listen'))
        script('ports-policy', 'tests/modules/ports/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('ports-policy'))
        port_options = (['--openssl-root', subprocess.check_output(['brew', '--prefix', 'openssl@3'], text=True).strip()]
                        if sys.platform == 'darwin' else [])
        for name in ['count', 'settings', 'defaults', 'callback_property', 'flags', 'packet_settings', 'options', 'tls_settings']:
            phase = 'ports-' + name.replace('_', '-')
            script(phase, 'tests/modules/ports/' + name + '.py', '--source', ROOT / 'target/upstream/src',
                   *(['--core', ROOT / 'target/hybrid' / native_variant / 'src'] if integrate else []), '--sanitize', *port_options,
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report(phase))
    if 'process' in modules:
        script('process-policy', 'tests/modules/process/gate.py',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('process-policy'))
    if 'ossupport' in modules:
        script('ossupport-policy', 'tests/modules/ossupport/gate.py',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('ossupport-policy'))
    if 'ossupport' in modules and integrate:
        script('ossupport-php', 'tests/modules/ossupport/php.py', '--manifest', manifest,
               '--source', ROOT / 'target/upstream/src', *php, *engines, *report('ossupport-php'))
    if 'coroutine' in modules and integrate:
        native_options = ['--php-prefix', subprocess.check_output(['php-config', '--prefix'], text=True).strip()] if sys.platform == 'darwin' else []
        if getattr(args, 'gtest_prefix', None):
            native_options += ['--gtest-prefix', args.gtest_prefix]
        script('coroutine-native-originals', 'tests/modules/coroutine/core.py', '--source', ROOT / 'target/upstream/src',
               '--config', manifest.parent / 'src/config.h',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--build-root', ROOT / 'target/native-originals/coroutine', '--jobs', args.jobs,
               '--sanitize', *native_options, *report('coroutine-native-originals'))
    if 'corebase' in modules:
        includes = (['--include', str(Path(subprocess.check_output(['brew', '--prefix', 'openssl@3'], text=True).strip()) / 'include')]
                    if sys.platform == 'darwin' else [])
        script('corebase-native', 'tests/modules/corebase/differential.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *includes, *report('corebase-native'))
        script('corebase-mkdir', 'tests/modules/corebase/mkdir.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *includes, *report('corebase-mkdir'))
        if integrate:
            script('corebase-php', 'tests/modules/corebase/php.py', '--source', ROOT / 'target/upstream/src',
                   *php, *engines, *report('corebase-php'))
            script('corebase-startup', 'tests/modules/corebase/mkdir_startup.py', *php, *engines, *report('corebase-startup'))
            native_options = (['--openssl-dir', subprocess.check_output(['brew', '--prefix', 'openssl@3'], text=True).strip(),
                               '--php-dir', subprocess.check_output(['php-config', '--prefix'], text=True).strip()]
                              if sys.platform == 'darwin' else [])
            if getattr(args, 'ccache', None):
                native_options += ['--ccache', args.ccache]
            else:
                native_options += ['--no-ccache']
            script('corebase-lifecycle', 'tests/modules/corebase/canonical.py', '--source', ROOT / 'target/upstream/src',
                   '--config', manifest.parent / 'src/config.h',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--jobs', args.jobs, *native_options, *report('corebase-lifecycle'))
    if 'tls' in modules:
        tls_options = ['--gtest-prefix', args.gtest_prefix] if getattr(args, 'gtest_prefix', None) else []
        if integrate and 'corebase' in modules:
            tls_options += ['--allocation-native-report', reports / 'corebase-lifecycle.json']
        script('tls-native', 'tests/modules/tls/gate.py', '--source', ROOT / 'target/upstream/src',
               '--config', manifest.parent / 'src/config.h',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--native-report', reports / 'coroutine-native-originals.json', '--jobs', args.jobs,
               *tls_options, *report('tls-native'))
    if 'framing' in modules:
        script('framing-native', 'tests/modules/framing/gate.py', '--archive',
               manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *report('framing-native'))
        script('framing-traces', 'tests/modules/framing/trace.py', *report('framing-traces'))
        if integrate:
            script('framing-versioned-expectation', 'corpus/upstream/versioned.py',
                   '--source', ROOT / 'target/upstream/src', '--case', 'tests/swoole_server/wrong_eof_setting.phpt',
                   *php_for('mbstring'), *engines, *report('framing-versioned-expectation'))
    if 'utilities' in modules:
        script('utilities-native', 'tests/modules/utilities/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *report('utilities-native'))
        script('utilities-bytes', 'tests/modules/utilities/bytes_gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('utilities-bytes'))
        script('utilities-put-threads', 'tests/modules/utilities/put.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', '--threads',
               *report('utilities-put-threads'))
        if sys.platform.startswith('linux'):  # Rust implements only the futex path; others run upstream's registry.
            script('utilities-wait', 'tests/modules/utilities/wait.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', *report('utilities-wait'))
    if 'utilities' in modules and integrate:
        utility_source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        utility_engines = ['--engine', f'hybrid={selected_export / "swoole.so"}',
                           '--engine', f'upstream={native_export / "swoole.so"}']
        for family in ['logger', 'hash', 'inline', 'global-logger', 'redirect']:
            name = 'utilities-' + family + '-originals'
            script(name, 'tests/modules/utilities/storage.py', '--source', ROOT / 'target/upstream/src',
                   *php_for('curl'), *utility_engines, '--build-manifest', manifest,
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
                   '--source-ref', utility_source, '--' + family + '-originals', *report(name))
        script('utilities-logger-owned-state', 'tests/modules/utilities/logger_state.py', '--source', ROOT / 'target/upstream/src',
               '--native-export', native_export, '--selected-export', selected_export,
               '--sdk-ref', utility_source,
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', *report('utilities-logger-owned-state'))
        script('utilities-lowercase-sdk', 'tests/modules/utilities/lowercase_sdk.py',
               '--source', ROOT / 'target/upstream/src', '--sdk-export', native_export / 'export.json',
               *report('utilities-lowercase-sdk'))
        script('utilities-lowercase-runtime', 'tests/modules/utilities/lowercase_runtime.py',
               '--source', manifest.parent / 'src', *php_for('sockets'), *engines,
               '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--source-ref', 'HEAD', *report('utilities-lowercase-runtime'))
        script('utilities-php-logger', 'tests/modules/utilities/php_logger.py', *php, *engines,
               '--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--source-ref', 'HEAD', *report('utilities-php-logger'))
        script('utilities-public-storage', 'tests/modules/utilities/storage.py', '--source', ROOT / 'target/upstream/src',
               *php, *utility_engines, '--build-manifest', manifest,
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               '--source-ref', utility_source, *report('utilities-public-storage'))
    if 'memory' in modules:
        script('memory-fixed-native-construction', 'tests/modules/memory/fixed_native_construction.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               *report('memory-fixed-native-construction'))
        script('memory-mapping-operation', 'tests/modules/memory/mapping_operation.py',
               '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               *report('memory-mapping-operation'))
        script('memory-table-v2-compatibility', 'tests/modules/memory/table_v2_compat.py',
               '--source', ROOT / 'target/upstream/src', *report('memory-table-v2-compatibility'))
        script('memory-source-compatibility', 'tests/modules/memory/channel_compat.py',
               '--source', ROOT / 'target/upstream/src', *report('memory-source-compatibility'))
        script('memory-native', 'tests/modules/memory/gate.py', '--extension', hybrid, '--php', args.php,
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a',
               *(['--sanitize'] if sys.platform == 'darwin' else []), *report('memory-native'))
    if 'memory' in modules and integrate:
        script('memory-table-witnesses', 'tests/modules/memory/witnesses.py', *php, *engines,
               '--require-memory-bridge', 'hybrid', *report('memory-table-witnesses'))
    if 'protocols' in modules:
        script('protocols-native', 'tests/modules/protocols/native.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize',
               *(['--allocation-failures'] if integrate else []), *report('protocols-native'))
        script('protocols-network', 'tests/modules/protocols/network.py', *php, *engines, *report('protocols-network'))
        if integrate:
            reference_first = ['--engine', f'upstream={reference}',
                               '--engine', f'hybrid={hybrid}']
            for name in ['reply', 'request', 'handlers', 'bailout']:
                script('protocols-' + name, 'tests/modules/protocols/' + name + '.py',
                       *php, *reference_first, *report('protocols-' + name))
            script('protocols-lifecycle', 'tests/modules/protocols/lifecycle.py',
                   *php, *reference_first, *report('protocols-lifecycle'))
    if 'timer' in modules:
        pytest('timer-fork-active', 'tests/modules/timer/test_fork.py', *php, *engines)
        if integrate:
            pytest('timer-bailout', 'tests/modules/timer/test_bailout.py', *php,
                   '--engine', f'upstream={reference}', '--engine', f'hybrid={hybrid}')
            pytest('timer-native', 'tests/modules/timer/test_adapter.py', '--manifest', manifest, *php,
                   *(['--sanitize'] if sys.platform == 'darwin' else []))
    if 'buffer' in modules:
        pytest('buffer-string-compatibility', 'tests/modules/buffer/string/test_compatibility.py',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize')
        if integrate and getattr(args, 'php_sockets', False):
            script('php-sockets-sendfile-original', 'corpus/upstream/run.py',
                   '--source', manifest.parent / 'src', '--manifest', ROOT / 'tests/modules/buffer/originals.json',
                   '--case', 'tests/swoole_server/sendfile_02.phpt', *php_for('curl', 'sockets'),
                   *engines, '--require-all', '--isolate-cases', *report('php-sockets-sendfile-original'))
        pytest('buffer-facade', 'tests/modules/buffer/test_facade.py', '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize')
        pytest('buffer-native', 'tests/modules/buffer/test_native.py', '--manifest', manifest, '--sanitize')
        pytest('buffer-callbacks', 'tests/modules/buffer/test_callbacks.py', '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a')
        pytest('buffer-posix-iovec', 'tests/modules/buffer/test_iovec.py', '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize')
        if integrate:
            # Typed Buffer refuses the mutable legacy front that the facade and storage consumers
            # use, so they run on a Buffer-only build, where the legacy facade still applies (#207).
            legacy_export = artifact_reports / 'legacy-buffer-export'
            if typed_buffer(args):
                script('buffer-legacy-build', 'tools/build_hybrid.py', '--module', 'buffer',
                       *(['--php-sockets'] if getattr(args, 'php_sockets', False) else []),
                       '--export', legacy_export, '--jobs', args.jobs,
                       *(['--native-build-root', args.native_build_root] if getattr(args, 'native_build_root', None) else []),
                       *(['--ccache', args.ccache] if getattr(args, 'ccache', None) else ['--no-ccache']))
            for consumer in ['random', 'storage', 'metadata', 'facade', 'copy', 'split', 'integer', 'ownership', 'allocation', 'format', 'compatibility']:
                name = 'string-production-' + consumer
                legacy = typed_buffer(args) and consumer in ('facade', 'storage')
                export = legacy_export if legacy else selected_export
                build = (['--build-manifest', export / 'build-manifest.json', '--archive', export / 'libswoole_rs_ffi.a'] if legacy else
                         ['--build-manifest', manifest, '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a'])
                script(name, 'tests/modules/buffer/string/production.py', '--source', ROOT / 'target/upstream/src',
                       *php, '--engine', f'hybrid={export / "swoole.so"}',
                       '--engine', f'upstream={native_export / "swoole.so"}',
                       '--borrow-immutable-exports', *build, '--source-ref', 'HEAD',
                       '--selected-export', export / 'export.json',
                       '--native-export', native_export / 'export.json', '--consumer', consumer, *report(name))
        for phase, profile in [('string-originals', '--original-only'), ('string-split', '--split-only'),
                               ('string-integer', '--integer-only'), ('string-ownership', '--ownership-only'),
                               ('string-allocation', '--allocation-only'), ('string-format', '--format-only'),
                               ('string-random', '--random-only')]:
            script(phase, 'tests/modules/buffer/string/gate.py', '--source', ROOT / 'target/upstream/src',
                   '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', profile,
                   *report(phase))
        script('string-copy', 'tests/modules/buffer/string/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', '--copy-only',
               *report('string-copy'))
        script('string-transitions', 'tests/modules/buffer/string/gate.py', '--source', ROOT / 'target/upstream/src',
               '--archive', manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a', '--sanitize', '--transition-only',
               *report('string-transitions'))
        if integrate:
            pytest('buffer-model', 'tests/modules/buffer/test_model.py', '--manifest', manifest, '--sanitize')
        pytest('buffer-network', 'tests/modules/buffer/test_network.py', *php, *engines)
    if 'websocket' in modules:
        archive = manifest.parent / 'src/../rust-prefix/lib/libswoole_rs_ffi.a'
        pytest('websocket-kernel', 'tests/modules/websocket/test_kernel.py', '--archive', archive, '--sanitize')
        pytest('websocket-codec', 'tests/modules/websocket/test_codec.py', '--archive', archive, '--sanitize')
        pytest('websocket-prefix', 'tests/modules/websocket/test_prefix.py', '--manifest', manifest, '--sanitize')
        pytest('websocket-differential', 'tests/modules/websocket/test_differential.py', *php,
               '--engine', f'upstream={reference}', '--engine', f'hybrid={hybrid}')
        pytest('websocket-invalid', 'tests/modules/websocket/test_invalid.py', *php, *engines)
        if integrate:
            pytest('websocket-close', 'tests/modules/websocket/test_close.py', *php, *engines)
    if repair:
        tls13_python = getattr(args, 'tls13_python', None) or python
        add('halfclose-tls13-driver', tls13_python, '-I', '-S', '-B', '-c', TLS13_PROBE)
        candidate = ['--engine', f'hybrid={hybrid}']
        script('halfclose-queued', 'tests/modules/halfclose/gate.py', *php, *candidate, *report('halfclose-queued'))
        script('halfclose-prequeue', 'tests/modules/halfclose/prequeue.py', *php, *candidate, *report('halfclose-prequeue'))
        script('halfclose-pressure', 'tests/modules/halfclose/prequeue.py', *php, *candidate,
               '--workers', '2', '--keep-alive', '--max-queued-bytes', '1', *report('halfclose-pressure'))
        for coroutines in [False, True]:
            name = 'halfclose-paused' + ('-coroutines' if coroutines else '')
            profile = ['--coroutines'] if coroutines else []
            script(name, 'tests/modules/halfclose/pause.py', *php, *candidate, *profile, *report(name))
            certs = ROOT / 'target/upstream/src/tests/include/ssl_certs'
            for version in ['1.2', '1.3']:
                tls_name = name + '-tls' + version
                add(tls_name, tls13_python if version == '1.3' else python, 'tests/modules/halfclose/pause.py', *php, *candidate, *profile,
                       '--tls-cert', certs / 'server.crt', '--tls-key', certs / 'server.key',
                       '--tls-version', version, *report(tls_name))
        script('halfclose-stale-read', 'tests/modules/halfclose/stale_read.py',
               '--source', manifest.parent / 'src', *report('halfclose-stale-read'))
        script('halfclose-pause-originals', 'corpus/upstream/run.py', *php, *candidate,
               '--manifest', 'tests/modules/halfclose/pause-originals.json', '--require-all',
               *report('halfclose-pause-originals'))
        openssl = (['--openssl-dir', subprocess.check_output(['brew', '--prefix', 'openssl@3'], text=True).strip()]
                   if sys.platform == 'darwin' else [])
        script('halfclose-tls-native', 'tests/modules/halfclose/tls_shutdown.py',
               '--source', manifest.parent / 'src', '--cert', certs / 'server.crt',
               '--key', certs / 'server.key', *openssl, *report('halfclose-tls-native'))
    if integrate and 'http' in modules:
        reference_first = ['--engine', f'upstream={reference}',
                           '--engine', f'hybrid={hybrid}']
        script('http-binding-reflection', 'tests/modules/http/binding_reflection.py',
               *php, *reference_first, *report('http-binding-reflection'))
    if integrate:
        script('applications', 'corpus/run.py', *php, *engines, '--require-all', *report('applications'))
    phpt = []
    if not integrate:
        if 'websocket' in modules:
            phpt += ['--module', 'websocket', '--module', 'websocket-network']
        if 'timer' in modules:
            phpt += ['--module', 'timers']
    if args.case and not integrate:
        phpt = [arg for case in args.case for arg in ['--case', case]]
    # The merge tier's phpt-* jobs run every pinned PHPT; this is for local runs only.
    # Buffer changes affect all queued network output; retain all PHPTs for it.
    if not integrate and ('buffer' in modules or phpt):
        script('phpt', 'corpus/upstream/run.py', '--source', manifest.parent / 'src', *php, *engines, *phpt, '--jobs', args.jobs,
               '--require-all', *(['--external-network'] if getattr(args, 'external_network', False) else []), *report('phpt'))
    if args.benchmark:
        # These phases are strictly after correctness checks and never concurrent.
        if 'timer' in modules:
            script('timer-benchmark', 'tests/modules/timer/benchmark.py', *php, *engines, *report('timer-benchmark'))
        if 'buffer' in modules:
            for peek in [False, True]:
                name = 'buffer-benchmark' + ('-consumer' if peek else '')
                script(name, 'tests/modules/buffer/benchmark.py', '--build-manifest', manifest,
                       *(['--peek-front'] if peek else []), *report(name))
        if 'websocket' in modules:
            script('websocket-benchmark', 'tests/modules/websocket/benchmark.py', *php, *engines, *report('websocket-benchmark'))
        if integrate:
            script('http-benchmark', 'benchmarks/run.py', *php, *engines, *report('http-benchmark'))
    return commands



def retain_build_manifest(build, reports):
    """Keep exact provenance readable after an ephemeral native world disappears."""
    original = Path(build['build_manifest'])
    manifest, digest = read_json(original, with_digest=True)
    retained = reports / 'build-manifest.json'
    copy_private(original, retained)
    if read_json(retained, with_digest=True)[1] != digest or read_json(original, with_digest=True)[1] != digest:
        raise ValueError('Build manifest changed during retention')
    identity = dict(original_path=str(original), path=str(retained), sha256=digest,
                    build_mode=manifest.get('build_mode'), source_ref=None)
    export = reports / 'selected-export/export.json'
    if export.is_file():
        receipt = read_json(export)
        if receipt['files']['build-manifest.json']['sha256'] != digest:
            raise ValueError('Export and retained build manifests differ')
        identity['source_ref'] = receipt['source_ref']
    return identity


# Phases that build artifacts later phases consume, or that later phases need to have
# passed. Each runs alone, after everything before it and before everything after it.
BARRIER_PHASES = {'ownership', 'build', 'reference-build', 'stdext-reference-build', 'buffer-legacy-build'}


def serial_phase(name):
    """Phases that can't share the machine: fixed ports (the PHPT runners), timing, benchmarks."""
    return (name == 'phpt' or name.endswith('-originals') or 'benchmark' in name or 'timing' in name)


def phase_dependencies(commands, reports):
    """A phase depends on every earlier barrier and on any earlier phase whose report it reads."""
    owners = {str(reports / (name + suffix)): name for name, _ in commands for suffix in ('.json', '.xml')}
    dependencies, barriers = {}, set()
    for name, command in commands:
        produced = {owners[str(arg)] for arg in command if str(arg) in owners} - {name}
        earlier = set(dependencies)
        dependencies[name] = (earlier if name in BARRIER_PHASES else barriers) | (produced & earlier)
        if name in BARRIER_PHASES:
            barriers.add(name)
    return dependencies


PHASE_WEIGHTS = ROOT / 'tools/phase_weights.json'  # seconds per phase from a merge-tier run
DEFAULT_WEIGHT = 2


def shard(commands, reports, index, count):
    """Every barrier (and what barriers read), plus the index-th of count groups of the other
    phases, balanced by weight. A phase always shares a shard with phases whose report it reads."""
    weights = json.loads(PHASE_WEIGHTS.read_text())
    owners = {str(reports / (name + suffix)): name for name, _ in commands for suffix in ('.json', '.xml')}
    reads = {name: {owners[str(arg)] for arg in command if str(arg) in owners} - {name} for name, command in commands}
    everywhere = set(BARRIER_PHASES)
    for name in [n for n, _ in commands if n in BARRIER_PHASES]:
        stack = list(reads[name])
        while stack:
            other = stack.pop()
            if other not in everywhere:
                everywhere.add(other)
                stack += reads[other]
    group = {name: name for name, _ in commands}
    def root(name):
        while group[name] != name:
            name = group[name]
        return name
    for name, needs in reads.items():
        for other in needs - everywhere:
            group[root(other)] = root(name)
    sizes = {}
    for name, _ in commands:
        if name not in everywhere:
            sizes[root(name)] = sizes.get(root(name), 0) + weights.get(name, DEFAULT_WEIGHT)
    load, slot = [0] * count, {}
    for unit in sorted(sizes, key=lambda unit: (-sizes[unit], unit)):
        slot[unit] = load.index(min(load))
        load[slot[unit]] += sizes[unit]
    return [(name, command) for name, command in commands if name in everywhere or slot[root(name)] == index - 1]


def shard_spec(value):
    index, _, count = value.partition('/')
    if not (index.isdigit() and count.isdigit() and 1 <= int(index) <= int(count)):
        raise argparse.ArgumentTypeError('expected I/N with 1 <= I <= N')
    return int(index), int(count)


def execute(command, *, timeout, **options):
    """subprocess.run in its own process group; on timeout the whole group (servers a phase
    started included) is killed and returncode is None."""
    process = subprocess.Popen(command, start_new_session=True, **options)
    try:
        return subprocess.CompletedProcess(command, process.wait(timeout=timeout))
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        return subprocess.CompletedProcess(command, None)


def schedule(commands, dependencies):
    """Plan order, except that serial phases nothing reads from move to the end of their
    barrier segment, so they don't drain the pipeline in the middle of parallel work."""
    needed = set().union(set(), *(d for n, d in dependencies.items() if n not in BARRIER_PHASES))
    ordered, deferred = [], []
    for phase in commands:
        name = phase[0]
        if name in BARRIER_PHASES:
            ordered += deferred
            deferred = []
            ordered.append(phase)
        elif serial_phase(name) and name not in needed:
            deferred.append(phase)
        else:
            ordered.append(phase)
    return ordered + deferred


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lane', choices=['edit', 'candidate', 'integrate'])
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--module', choices=SELECTABLE, action='append')
    selection.add_argument('--all-modules', action='store_true', help='Select every concrete registered Rust module')
    selection.add_argument('--changed-since', metavar='REF', help='Select the modules a diff from REF touches (all for shared build inputs)')
    parser.add_argument('--stdext', action='store_true', help='Build and compare genuine enabled experimental stdext profiles')
    parser.add_argument('--php-sockets', action='store_true', help='Build matching Native/Rust PHP sockets-integration profiles')
    parser.add_argument('--external-network', action='store_true',
                        help='Also run original PHPTs that need internet access; without it they stay unmeasured')
    parser.add_argument('--fix-halfclose', action='store_true', help='Select the separate native queued-close drain repair')
    parser.add_argument('--test', help='Rust test-name filter (edit lane only)')
    parser.add_argument('--case', action='append', help='Exact registered PHPT path (candidate lane only)')
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 4,
                        help='Phases run at once, and parallelism passed to builds (default: CPU count)')
    parser.add_argument('--php', default='php')
    parser.add_argument('--match-child-php', action='store_true',
                        help='Bind bare php children in direct official-runner phases to their selected parent; default off')
    parser.add_argument('--tls13-python', type=Path, help='Explicit Python SSL provider for native-repair TLS1.3 clients only; defaults to this driver, without fallback')
    parser.add_argument('--ccache', type=Path, default=shutil.which('ccache'), help='Shared compiler cache executable, detected by default')
    parser.add_argument('--no-ccache', dest='ccache', action='store_const', const=None)
    parser.add_argument('--native-build-root', type=Path, help='Private location for native hybrid worlds; space guard remains enforced')
    parser.add_argument('--gtest-prefix', type=Path, help='Read-only C++14-compatible GoogleTest prefix for native originals')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--redis-extension', type=Path, help='Explicit Redis-enabled full original collection profile, retaining baseline phases')
    parser.add_argument('--redis-image', help='Immutable Redis Docker image for that profile; otherwise use managed native service')
    parser.add_argument('--hypothesis', help='What this experiment should establish')
    parser.add_argument('--expect', help='Observable outcome that supports the hypothesis')
    parser.add_argument('--benchmark', action='store_true', help='Run isolated benchmarks after all correctness phases pass')
    parser.add_argument('--compare', action='store_true', help='Also rerun upstream controls in the candidate lane (integration always does)')
    parser.add_argument('--phase', action='append', help='Run named canonical phases only; omitted gates remain explicitly not run and cannot qualify full integration')
    parser.add_argument('--phase-timeout', type=int, default=1200, metavar='SECONDS',
                        help='Kill a phase (and the processes it started) after this long; it fails')
    parser.add_argument('--shard', type=shard_spec, metavar='I/N',
                        help='Run slice I of N of the integrate plan; every slice builds and runs the barriers')
    parser.add_argument('--artifacts-from', type=Path, help='Reuse verified exports from an existing same-source report for explicit correctness phases; never reuse test outcomes')
    parser.add_argument('--frozen-source', help='Require this literal 40-hex HEAD and a clean checkout before and after each integration phase')
    parser.add_argument('--plan', action='store_true', help='Print commands without executing or writing reports')
    args = parser.parse_args()
    if args.changed_since:
        args.module = changed_modules(args.changed_since)
        if not args.module:
            print('No module touched since ' + args.changed_since)
            return 0
        print('Modules touched since ' + args.changed_since + ': ' + ', '.join(args.module))
    if args.frozen_source and (args.lane != 'integrate' or len(args.frozen_source) != 40
                               or any(c not in '0123456789abcdef' for c in args.frozen_source)):
        parser.error('--frozen-source requires integration and a literal lowercase 40-hex commit')
    if args.jobs < 1 or args.test and args.lane != 'edit' or args.case and args.lane != 'candidate':
        parser.error('Positive --jobs required; --test is edit-only and --case is candidate-only')
    if args.redis_image and not args.redis_extension:
        parser.error('--redis-image requires the explicit --redis-extension profile')
    if args.benchmark and args.lane == 'edit':
        parser.error('Benchmarks require candidate or integrate')
    if args.phase and (args.lane == 'edit' or args.benchmark):
        parser.error('--phase requires candidate/integrate and cannot qualify a benchmark run')
    artifact_identity = None
    if args.shard and (args.lane != 'integrate' or args.phase):
        parser.error('--shard splits the full integrate plan; it cannot be combined with --phase')
    if args.artifacts_from:
        if args.lane != 'integrate' or not args.phase or set(args.phase) & {'build', 'reference-build', 'stdext-reference-build', 'buffer-legacy-build'}:
            parser.error('--artifacts-from requires explicit integration phases without builds')
        try:
            args.artifacts_from = args.artifacts_from.resolve()
            artifact_identity = verify_artifact_report(args)
        except (ValueError, KeyError, OSError) as error:
            parser.error(str(error))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    reports = ROOT / 'target/reports/dev' / stamp
    planned = plan(args, reports)
    if args.phase:
        unknown = set(args.phase) - {name for name, _ in planned}
        if unknown:
            parser.error('Unknown phases: ' + ', '.join(sorted(unknown)))
        report_owners = {str(reports / (name + '.json')): name for name, _ in planned}
        for name, command in planned:
            if name in args.phase:
                missing = {report_owners[arg] for arg in command if arg in report_owners} - set(args.phase) - {name}
                if missing:
                    parser.error('--phase ' + name + ' requires report-producing phases in the same run: '
                                 + ', '.join(sorted(missing)))
    commands = [(name, command) for name, command in planned if not args.phase or name in args.phase]
    if args.shard:
        commands = shard(commands, reports, *args.shard)
    if args.plan:
        print(json.dumps([{'phase': name, 'command': command} for name, command in commands], indent=2))
        return 0
    reports.mkdir(parents=True)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'lane': args.lane,
              'hypothesis': args.hypothesis, 'expected_observation': args.expect,
              'match_child_php_requested': args.match_child_php, 'frozen_source_required': args.frozen_source,
              'phases': [], 'status': 'running', 'selection_scope': 'explicit_phase_subset' if args.phase else 'complete_plan',
              'planned_phases': [name for name, _ in planned], 'selected_phases': [name for name, _ in commands],
              'full_plan_passed': False, 'reused_artifacts': artifact_identity,
              'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    environment = dict(os.environ)
    def frozen_error():
        if args.frozen_source:
            try:
                require_frozen_source(args.frozen_source)
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                return str(error)
        return None

    started = time.monotonic()
    order = {name: index for index, (name, _) in enumerate(commands)}
    dependencies = phase_dependencies(commands, reports)
    lock = threading.Condition()
    running, finished = set(), set()

    def run_phase(name, command):
        print(f'[{name}] {shlex.join(command)}', flush=True)
        phase_started = time.monotonic()
        with (reports / (name + '.log')).open('w') as log:
            result = execute(command, timeout=args.phase_timeout, cwd=ROOT, env=environment, stdout=log,
                             stderr=subprocess.STDOUT)
            if result.returncode is None:
                log.write(f'\ndev.py: phase timed out after {args.phase_timeout}s and was killed\n')
        row = {'phase': name, 'command': command, 'seconds': round(time.monotonic() - phase_started, 4),
               'returncode': result.returncode, 'failed': result.returncode != 0, 'log': str(reports / (name + '.log'))}
        if result.returncode is None:
            row['timed_out'] = True
        outcome_flag = next((flag for flag in ('--output', '--report') if flag in command), None)
        if outcome_flag:
            path = Path(command[command.index(outcome_flag) + 1])
            if not path.is_absolute():
                path = ROOT / path
            try:
                outcome, row['outcome_sha256'] = read_json(path, with_digest=True)
                if 'passed' in outcome:
                    row['outcome_passed'] = outcome['passed']
                    if not isinstance(outcome['passed'], bool):
                        raise ValueError('Gate passed field must be boolean')
                    row['failed'] |= not outcome['passed']
                if 'compile' in outcome:
                    row['compile'] = outcome['compile']
                error = outcome.get('error')
                compiler_guard = error == 'Compiler refused by unchanged 4GiB guard' and any(
                    isinstance(command, dict) and command.get('blocked') == 'unchanged 4GiB guard'
                    and isinstance(command.get('free_bytes'), dict) and any(
                        type(free) is int and 0 <= free < 4 * 1024**3
                        for free in command['free_bytes'].values())
                    for command in (outcome.get('commands') if isinstance(outcome.get('commands'), list) else []))
                disk_refused = isinstance(error, str) and (error.startswith('Build disk space low:')
                    or error in {'Unchanged 4GiB guard', 'Unchanged4GiBguard'}
                    and outcome.get('minimum_free_bytes') == 4 * 1024**3 and bool(outcome.get('blocked')))
                if row['failed'] and (disk_refused or compiler_guard):
                    row['infrastructure_error'] = error
            except (OSError, ValueError) as error:
                row.update(failed=True, outcome_error=str(error))
        if name == 'build' and result.returncode == 0:
            variant = build_variant(args)
            row['build'] = json.loads((ROOT / 'target/hybrid' / variant / 'last-run.json').read_text())
            try:
                row['build']['retained_manifest'] = retain_build_manifest(row['build'], reports)
            except (OSError, ValueError, KeyError) as error:
                row.update(failed=True, outcome_error='Build provenance retention failed: ' + str(error))
        print(f'  [{name}] {row["seconds"]:.3f}s; exit={result.returncode}; failed={row["failed"]}; {row["log"]}', flush=True)
        return row

    def record(row):
        # Called with `lock` held. Rows stay in plan order whatever order phases finish in.
        name = row['phase']
        error = row.pop('infrastructure_error', None)
        source = frozen_error()
        if source:
            row.update(failed=True, source_error=source)
            error = error or source
        if error:
            report.update(infrastructure_error=error, blocked_phase=name)
        report['phases'].append(row)
        report['phases'].sort(key=lambda r: order[r['phase']])
        write_report(reports / 'loop.json', report)
        if row['failed'] and name in BARRIER_PHASES or report.get('infrastructure_error'):
            report['blocked_phase'] = name
            return True
        return bool(row['failed'] and args.lane != 'integrate')

    def worker(name, command):
        try:
            row = run_phase(name, command)
        except Exception as error:  # a dead worker would leave the scheduler waiting forever
            row = {'phase': name, 'command': command, 'seconds': 0, 'returncode': None, 'failed': True,
                   'log': str(reports / (name + '.log')), 'outcome_error': f'dev.py: {type(error).__name__}: {error}'}
        with lock:
            running.discard(name)
            finished.add(name)
            if record(row):
                pending.clear()
            lock.notify_all()

    pending = schedule(commands, dependencies)
    # A frozen source is checked between phases, so a change is attributed to exactly one.
    concurrency = 1 if args.frozen_source else args.jobs
    threads = []
    try:
        with lock:
            while pending or running:
                ready = None
                for name, command in pending:
                    exclusive = name in BARRIER_PHASES or serial_phase(name)
                    if dependencies[name] <= finished and not (running and exclusive) \
                            and not any(other in BARRIER_PHASES or serial_phase(other) for other in running) \
                            and len(running) < concurrency:
                        ready = (name, command)
                        break
                    if exclusive:
                        break  # Never let later phases overtake a barrier or serial phase.
                if ready is None:
                    lock.wait()
                    continue
                name, command = ready
                pending.remove(ready)
                error = frozen_error()
                if error:
                    report.update(infrastructure_error=error, blocked_phase=name)
                    pending.clear()
                    continue
                if name.endswith('-unit') or name == 'build':
                    try:
                        require_build_space(ROOT)
                    except (RuntimeError, ValueError) as error:
                        report.update(infrastructure_error=str(error), blocked_phase=name)
                        pending.clear()
                        continue
                if 'benchmark' in name and any(row['failed'] for row in report['phases']):
                    report['benchmarks_skipped'] = 'Correctness failed; preserve the failure before measuring'
                    pending.clear()
                    continue
                running.add(name)
                thread = threading.Thread(target=worker, args=(name, command), daemon=True)
                threads.append(thread)
                thread.start()
        for thread in threads:
            thread.join()
        failed = report.get('infrastructure_error') or any(row['failed'] for row in report['phases'])
        report['status'] = ('partial_failed' if failed else 'partial_passed') if args.phase else ('failed' if failed else 'passed')
        report['full_plan_passed'] = not args.phase and not failed and len(report['phases']) == len(planned)
    finally:
        if report['status'] == 'running':
            report['status'] = 'interrupted'
        executed = {row['phase'] for row in report['phases']}
        selected = {name for name, _ in commands}
        report['not_run'] = [{'phase': name, 'status': 'not_run',
                              'reason': 'explicit_phase_selection' if name not in selected else 'run_stopped_before_phase'}
                             for name, _ in planned if name not in executed]
        report['seconds'] = round(time.monotonic() - started, 4)
        write_report(reports / 'loop.json', report)
        print(f'Loop: {reports / "loop.json"}', flush=True)
        failures = [row for row in report['phases'] if row['failed']]
        if failures:
            lines = [f'{len(failures)} of {len(report["phases"])} phases failed:'] + [
                f'- {row["phase"]} (exit {row.get("returncode")}): {row.get("log")}' for row in failures]
            print(*lines, sep='\n', flush=True)
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                    summary.write('### Failed phases\n\n' + '\n'.join(lines) + '\n\n')
    return int(report['status'] not in {'passed', 'partial_passed'})


if __name__ == '__main__':
    sys.exit(main())
