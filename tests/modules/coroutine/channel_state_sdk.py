#!/usr/bin/env python3
"""Compile actual Channel core/PHP consumers and layouts in copied configured SDKs.
No extension load, Channel operation, Coroutine/context or PHP execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid
from ordered_gate import ROOT, PIN
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report
from tools.private_copy import copy_private


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture_sdk(export_path, target):
    """Copy exact producer SDK inputs once; all later compilers use private files."""
    exported = json.loads(export_path.read_text())
    for name, item in exported['files'].items():
        if sha(export_path.parent / name) != item['sha256']:
            raise ValueError('Immutable export changed: ' + name)
    manifest = Path(exported['files']['build-manifest.json']['source'])
    source = (manifest.parent / 'src').resolve()
    prefix = (source / '../rust-prefix/include').resolve()
    files = list(source.glob('*.h')) + [source / 'Makefile']
    for folder in ['include', 'ext-src', 'thirdparty']:
        files.extend(p for p in (source / folder).rglob('*') if p.is_file() and p.suffix in ['.h', '.hpp', '.inc'])
    files.extend(source / name for name in ['src/coroutine/base.cc', 'src/coroutine/channel.cc',
                 'src/coroutine/context.cc', 'src/coroutine/thread_context.cc', 'ext-src/swoole_channel_coro.cc'])
    before = {str(p): sha(p) for p in set(files)}
    prefix_before = {str(p): sha(p) for p in prefix.rglob('*.h')} if prefix.exists() else {}
    copied = {}
    for inputs, base, destination in [(before, source, target), (prefix_before, prefix, target / 'ffi-include')]:
        for path, digest in inputs.items():
            original = Path(path)
            private = destination / original.relative_to(base)
            private.parent.mkdir(parents=True, exist_ok=True)
            copy_private(original, private)
            if sha(private) != digest:
                raise ValueError('SDK copy changed')
            copied[str(private)] = digest
    if any(sha(path) != digest for path, digest in {**before, **prefix_before}.items()):
        raise ValueError('Producer changed during short read-only SDK capture')
    return dict(source=str(source), prefix=str(prefix), directory=str(target),
                copied_sha256=copied, source_before_after_sha256=before,
                prefix_before_after_sha256=prefix_before, source_ref=exported['source_ref'],
                producer_borrow_released=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'report']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sdk-snapshot', type=Path, help='Previously captured private SDK snapshot')
    parser.add_argument('--backend', choices=['header-default', 'asm', 'ucontext', 'thread'], default='header-default',
                        help='Optional private SDK-only backend projection; no configured world/runtime claim')
    parser.add_argument('--registry-v2', action='store_true', help='Explicit qualified policy SDK-only projection; no runtime/default activation')
    parser.add_argument('--sdk-export', type=Path, help='Actual immutable selected export.json')
    parser.add_argument('--native-export', type=Path, help='Actual immutable Native export.json')
    args = parser.parse_args()
    if bool(args.sdk_export) != bool(args.native_export) or bool(args.sdk_snapshot) == bool(args.sdk_export):
        parser.error('Require either private --sdk-snapshot or both selected/native exports')
    output = args.report.resolve()
    if output.exists():
        parser.error('Use a unique receipt')
    work = output.parent / ('channel-state-sdk-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, work=str(work), commands=[], layouts=[], coroutine_layouts=[], context_layouts=[],
                  backend_projection=args.backend, registry_v2_projection=args.registry_v2,
                  runtime_executed=False, full_gate_passed=False,
                  limits=['Private configured SDK plus current verified M06 projection; no producer-source/runtime credit.',
                          'M06-only derives the feature flag from actual Native configuration; it is not a separately built production world.',
                          'Only layout executables run; they instantiate no Channel or native context. Linux/ZTS/runtime/lifetime/performance remain open.'])
    bound_paths = [Path(__file__), Path(__file__).with_name('channel_state_layout.cc'),
                   ROOT / 'migration/patches/coroutine/manifest.json',
                   *sorted((ROOT / 'native/coroutine').glob('*.h')),
                   *sorted((ROOT / 'crates/coroutine/src').glob('*.rs'))]
    bound_paths.append(Path(__file__).with_name('timing_layout.cc'))
    bound_paths.append(Path(__file__).with_name('context_layout.cc'))
    bound_paths.append(Path(__file__).with_name('identity_source.py'))
    bound_paths.append(Path(__file__).with_name('swap_source.py'))
    bound_paths.append(Path(__file__).with_name('make_coroutine_swap.py'))
    bound_paths.append(Path(__file__).with_name('print_source.py'))
    bound_paths.append(Path(__file__).with_name('make_coroutine_print.py'))
    bound_paths.append(Path(__file__).with_name('entry_source.py'))
    bound_paths.append(Path(__file__).with_name('make_coroutine_entry.py'))
    bound_paths.append(Path(__file__).with_name('bailout_source.py'))
    bound_paths.append(Path(__file__).with_name('make_coroutine_bailout.py'))
    bound_paths.append(Path(__file__).with_name('creation_source.py'))
    bound_paths.append(Path(__file__).with_name('make_coroutine_creation.py'))
    entries = json.loads(bound_paths[2].read_text())['patches']
    bound_paths += [bound_paths[2].parent / entry['path'] for entry in entries]
    identities = {str(p.resolve()): sha(p) for p in bound_paths}
    report['owned_inputs_sha256'] = identities
    try:
        require_build_space(work)
        if args.sdk_snapshot:
            snapshot = json.loads(args.sdk_snapshot.read_text())
        else:
            engines = {name: capture_sdk(path, work / ('input-' + name)) for name, path in [('native', args.native_export), ('combined', args.sdk_export)]}
            snapshot = dict(source_ref=engines['combined']['source_ref'], engines=engines)
            (work / 'captured-sdk.json').write_text(json.dumps(snapshot, indent=2) + '\n')
        report['sdk_config_source_ref'] = snapshot['source_ref']
        for engine in snapshot['engines'].values():
            if any(sha(path) != digest for path, digest in engine['copied_sha256'].items()):
                raise ValueError('Captured private SDK changed')
        patchroot = work / 'current-m06'
        for entry in entries:
            for name in entry['upstream_paths']:
                path = patchroot / name
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':' + name]))
        report['patch_proofs'] = [apply_patch_verified(patchroot, bound_paths[2].parent / entry['path'], entry['upstream_paths'], entry['sha256']) for entry in entries]
        units = ['src/coroutine/base.cc', 'src/coroutine/channel.cc', 'src/coroutine/context.cc',
                 'src/coroutine/thread_context.cc', 'ext-src/swoole_channel_coro.cc']
        report['profiles'] = []
        native_class = {}
        native_coroutine = {}
        native_context = {}
        for profile in ['native', 'disabled', 'm06', 'combined']:
            original = snapshot['engines']['combined' if profile == 'combined' else 'native']
            base = Path(original['directory'])
            tree = work / profile
            for path in base.rglob('*'):
                if path.is_file():
                    target = tree / path.relative_to(base)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copy_private(path, target)
            if profile != 'native':
                for entry in entries:
                    for name in entry['upstream_paths']:
                        if profile != 'disabled' or name.endswith('.h'):
                            copy_private(patchroot / name, tree / name)
            if profile == 'm06':
                config = tree / 'config.h'
                config.write_text(config.read_text() + '\n/* Explicit private M06-only SDK projection. */\n#undef SWOOLE_RS_COROUTINE\n#define SWOOLE_RS_COROUTINE 1\n')
            if args.registry_v2 and profile in ['m06', 'combined']:
                config = tree / 'config.h'
                config.write_text(config.read_text() + '\n/* Explicit SDK-only registry projection. */\n#undef SWOOLE_RS_COROUTINE_REGISTRY_V2\n#define SWOOLE_RS_COROUTINE_REGISTRY_V2 1\n')
            if args.backend != 'header-default':
                config = tree / 'config.h'
                config.write_text(config.read_text() + '\n/* Explicit SDK-only backend; not a configured runtime. */\n#undef SW_USE_THREAD_CONTEXT\n#undef SW_USE_ASM_CONTEXT\n' +
                                  {'asm': '#define SW_USE_ASM_CONTEXT 1\n', 'thread': '#define SW_USE_THREAD_CONTEXT 1\n', 'ucontext': ''}[args.backend])
            variables = {line.split('=', 1)[0].strip(): line.split('=', 1)[1].strip()
                         for line in (tree / 'Makefile').read_text().splitlines() if '=' in line}
            includes = shlex.split(variables['INCLUDES'])
            includes = [part.replace(original['source'], str(tree)).replace(original['prefix'], str(tree / 'ffi-include')) for part in includes]
            flags = [*shlex.split(variables['CXXFLAGS']), *shlex.split(variables['CPPFLAGS'])]
            report['profiles'].append(dict(name=profile))
            for standard in ['c++14', 'c++17']:
                common = ['c++', *flags, '-std=' + standard, '-Werror', '-fPIC', '-DENABLE_PHP_SWOOLE',
                          '-DZEND_COMPILE_DL_EXT=1', '-DHAVE_CONFIG_H', '-I' + str(ROOT / 'native/coroutine'), *includes]
                if profile in ['native', 'disabled']:
                    probe = work / ('fallback-' + profile + '-' + standard + '.cc')
                    probe.write_text('#include "swoole_coroutine_channel.h"\n')
                    preprocessed = run_isolated([*common, '-E', '-P', str(probe)], cwd=tree, timeout=120)
                    if preprocessed.returncode or preprocessed.stderr:
                        raise ValueError('Native fallback preprocessing failed')
                    from ordered_gate import block
                    text = ' '.join(block(preprocessed.stdout, 'class Channel {').split())
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    if profile == 'native':
                        native_class[standard] = digest
                    elif digest != native_class[standard]:
                        raise ValueError('Disabled patched public Channel differs from complete Native class')
                    text = ' '.join(block(preprocessed.stdout, 'class Coroutine {').split())
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    if profile == 'native':
                        native_coroutine[standard] = digest
                    elif digest != native_coroutine[standard]:
                        raise ValueError('Disabled patched complete Coroutine differs from Native')
                    text = ' '.join(block(preprocessed.stdout, 'class Context {').split())
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    if profile == 'native':
                        native_context[standard] = digest
                    elif digest != native_context[standard]:
                        raise ValueError('Disabled patched complete Context differs from Native')
                for unit in ([] if profile == 'disabled' else units):
                    obj = work / (profile + '-' + standard + '-' + Path(unit).stem + '.o')
                    command = [*common, '-MMD', '-MF', str(obj) + '.d', '-c', str(tree / unit), '-o', str(obj)]
                    require_build_space(work)
                    result = run_isolated(command, cwd=tree, timeout=120)
                    row = dict(profile=profile, standard=standard, unit=unit, command=command,
                               exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
                    report['commands'].append(row)
                    write_report(output, report)
                    if result.returncode or result.stderr:
                        raise ValueError('Whole actual consumer failed or warned')
                    dependencies = shlex.split(Path(str(obj) + '.d').read_text().replace('\\\n', ' ').split(':', 1)[1])
                    row['dependencies'] = sorted({str((Path(name) if Path(name).is_absolute() else tree / name).resolve()) for name in dependencies})
                    if unit.endswith(('channel.cc', 'swoole_channel_coro.cc')):
                        header = str((tree / 'include/swoole_coroutine_channel.h').resolve())
                        if header not in row['dependencies']:
                            raise ValueError('Actual Channel consumer missed assigned header')
                    symbols = run_isolated(['nm', '-u', str(obj)], timeout=20)
                    if symbols.returncode or symbols.stderr:
                        raise ValueError('Actual object symbol observation failed')
                    imports = sorted({line.split()[-1].lstrip('_') for line in symbols.stdout.splitlines() if 'swr_v1_channel_' in line})
                    row.update(channel_imports=imports)
                    status_imports = sorted({line.split()[-1].lstrip('_') for line in symbols.stdout.splitlines() if 'swr_v1_coroutine_status_' in line})
                    row['coroutine_status_imports'] = status_imports
                    context_imports = sorted({line.split()[-1].lstrip('_') for line in symbols.stdout.splitlines() if 'swr_v1_context_' in line})
                    row['context_imports'] = context_imports
                    identity_imports = sorted({line.split()[-1].lstrip('_') for line in symbols.stdout.splitlines() if 'swr_v1_coroutine_identity_' in line})
                    row['identity_imports'] = identity_imports
                    swap_imports = sorted({line.split()[-1].lstrip('_') for line in symbols.stdout.splitlines() if 'swr_v1_coroutine_swap_' in line or 'swr_v1_coroutine_dispatch' in line})
                    row['swap_imports'] = swap_imports
                    creation_imports = sorted({line.split()[-1].lstrip('_') for line in symbols.stdout.splitlines() if any(name in line for name in ['swr_v1_coroutine_registry_print_step', 'swr_v1_coroutine_entry_step', 'swr_v1_coroutine_bailout_step', 'swr_v1_coroutine_create_step', 'swr_v1_coroutine_selected_create_step', 'swr_v1_coroutine_cid_read', 'swr_v1_coroutine_unregister', 'swr_v1_coroutine_registry_lookup'])})
                    row['creation_imports'] = creation_imports
                    required_creation = {'swr_v1_coroutine_entry_step', 'swr_v1_coroutine_bailout_step', 'swr_v1_coroutine_cid_read', 'swr_v1_coroutine_selected_create_step' if args.registry_v2 else 'swr_v1_coroutine_create_step'}
                    if args.registry_v2:
                        required_creation |= {'swr_v1_coroutine_registry_print_step', 'swr_v1_coroutine_unregister', 'swr_v1_coroutine_registry_lookup'}
                    if profile != 'native' and unit == 'src/coroutine/base.cc' and not required_creation.issubset(creation_imports):
                        raise ValueError('Actual creation/CID/lookup/removal caller closure missed Rust owner')
                    if profile == 'native' and creation_imports:
                        raise ValueError('Creation owner leaked into Native fallback')
                    if profile != 'native' and unit == 'src/coroutine/base.cc' and not {'swr_v1_coroutine_swap_publish', 'swr_v1_coroutine_dispatch'}.issubset(swap_imports):
                        raise ValueError('Actual lifecycle dispatch/setter missed typed Rust owner')
                    if profile == 'native' and swap_imports:
                        raise ValueError('Swap owner leaked into Native fallback')
                    if profile != 'native' and unit == 'src/coroutine/base.cc' and not {'swr_v1_coroutine_identity_read', 'swr_v1_coroutine_identity_publish', 'swr_v1_coroutine_identity_route'}.issubset(identity_imports):
                        raise ValueError('Actual identity caller closure missed Rust custody')
                    if profile == 'native' and identity_imports:
                        raise ValueError('Identity owner leaked into Native fallback')
                    if profile != 'native' and unit == 'src/coroutine/base.cc' and 'swr_v1_context_completed' not in context_imports:
                        raise ValueError('Actual Core missed sole completion-cell readout')
                    if profile == 'native' and context_imports:
                        raise ValueError('Context owner leaked into Native fallback')
                    # V2 whole print reads via the same private status kernel,
                    # replacing the last Native public get_state/read call.
                    required_status = {'swr_v1_coroutine_status_transition'}
                    if not args.registry_v2:
                        required_status.add('swr_v1_coroutine_status_read')
                    if profile != 'native' and unit == 'src/coroutine/base.cc' and not required_status.issubset(status_imports):
                        raise ValueError('Actual lifecycle callers missed sole status owner')
                    if profile == 'native' and status_imports:
                        raise ValueError('Status owner leaked into Native fallback')
                    if profile == 'native' and imports:
                        raise ValueError('Rust leaked into Native source')
                    if profile != 'native' and unit == 'src/coroutine/channel.cc' and 'swr_v1_channel_owned_step' not in imports:
                        raise ValueError('Actual core missed coupled Rust caller')
                    if profile != 'native' and unit == 'src/coroutine/channel.cc' and 'swr_v1_channel_waiter' not in imports:
                        raise ValueError('Actual core missed whole waiter caller')
                    if profile != 'native' and unit == 'ext-src/swoole_channel_coro.cc' and not {'swr_v1_channel_state_new', 'swr_v1_channel_view_read', 'swr_v1_channel_pop_data'}.issubset(imports):
                        raise ValueError('Actual PHP consumer missed complete constructor/query/data imports')
                binary = work / (profile + '-' + standard + '-layout')
                command = [*common, Path(__file__).with_name('channel_state_layout.cc'), '-o', binary]
                require_build_space(work)
                compiled = run_isolated(list(map(str, command)), cwd=tree, timeout=120)
                row = dict(profile=profile, standard=standard, command=list(map(str, command)), exit=compiled.returncode,
                           stdout=compiled.stdout, stderr=compiled.stderr)
                report['layouts'].append(row)
                write_report(output, report)
                if compiled.returncode or compiled.stderr:
                    raise ValueError('Full selected layout verification failed')
                observed = run_isolated([str(binary)], timeout=10)
                if observed.returncode or observed.stderr:
                    raise ValueError('Inert layout observation failed')
                row.update(layout=json.loads(observed.stdout))
                binary = work / (profile + '-' + standard + '-context-layout')
                command = [*common, '-Wno-invalid-offsetof', Path(__file__).with_name('context_layout.cc'), '-o', binary]
                require_build_space(work)
                compiled = run_isolated(list(map(str, command)), cwd=tree, timeout=120)
                row = dict(profile=profile, standard=standard, command=list(map(str, command)), exit=compiled.returncode,
                           stdout=compiled.stdout, stderr=compiled.stderr,
                           scope='Complete compiler-supported layout; no Context object construction')
                report['context_layouts'].append(row)
                write_report(output, report)
                if compiled.returncode or compiled.stderr:
                    raise ValueError('Complete Context layout failed')
                observed = run_isolated([str(binary)], timeout=10)
                if observed.returncode or observed.stderr:
                    raise ValueError('Inert Context layout observation failed')
                row.update(layout=json.loads(observed.stdout))
                binary = work / (profile + '-' + standard + '-coroutine-layout')
                command = [*common, '-Wno-invalid-offsetof', Path(__file__).with_name('timing_layout.cc'), '-o', binary]
                require_build_space(work)
                compiled = run_isolated(list(map(str, command)), cwd=tree, timeout=120)
                row = dict(profile=profile, standard=standard, command=list(map(str, command)), exit=compiled.returncode,
                           stdout=compiled.stdout, stderr=compiled.stderr,
                           scope='Compiler-supported offsetof for complete nonstandard-layout Native class; no object construction')
                report['coroutine_layouts'].append(row)
                write_report(output, report)
                if compiled.returncode or compiled.stderr:
                    raise ValueError('Complete Coroutine layout failed')
                observed = run_isolated([str(binary)], timeout=10)
                if observed.returncode or observed.stderr:
                    raise ValueError('Inert Coroutine layout observation failed')
                row.update(layout=json.loads(observed.stdout))
        # Explicit zero must preserve this batch's exact preexisting header
        # semantics; older M06 guards are intentionally outside this amendment.
        from identity_source import restore_identity, GUARD
        tree = work / 'm06'
        zero = work / 'identity-zero' / 'config.h'
        zero.parent.mkdir()
        zero.write_text('#ifndef SWR_IDENTITY_ZERO_CONFIG\n#define SWR_IDENTITY_ZERO_CONFIG 1\n' +
                        (tree / 'config.h').read_text() + '\n#undef SWOOLE_RS_COROUTINE\n#define SWOOLE_RS_COROUTINE 0\n#endif\n')
        before_header = work / 'identity-before.h'
        before_header.write_text(restore_identity((tree / 'include/swoole_coroutine.h').read_text()).replace(GUARD, '', 1))
        report['identity_zero_fallback'] = []
        for standard in ['c++14', 'c++17']:
            digests = []
            for header in [before_header, tree / 'include/swoole_coroutine.h']:
                probe = work / ('identity-zero-' + standard + '-' + header.name + '.cc')
                probe.write_text('#include "' + str(header) + '"\n')
                command = ['c++', *flags, '-std=' + standard, '-Werror', '-DENABLE_PHP_SWOOLE',
                           '-DZEND_COMPILE_DL_EXT=1', '-DHAVE_CONFIG_H', '-I' + str(ROOT / 'native/coroutine'),
                           '-I' + str(zero.parent), '-I' + str(tree / 'include'), '-include', str(zero), *includes, '-E', '-P', str(probe)]
                # includes came from combined; relocate only its private SDK path.
                command = [part.replace(str(work / 'combined'), str(tree)) for part in command]
                require_build_space(work)
                result = run_isolated(command, cwd=tree, timeout=120)
                row = dict(standard=standard, header=str(header), command=command, exit=result.returncode,
                           stdout=result.stdout, stderr=result.stderr)
                report['identity_zero_fallback'].append(row)
                write_report(output, report)
                if result.returncode or result.stderr:
                    raise ValueError('Explicit-zero identity header preprocessing failed')
                text = ' '.join(block(result.stdout, 'class Coroutine {').split())
                digests.append(text)
            if digests[0] != digests[1]:
                raise ValueError('Identity amendment changed explicit-zero preexisting class')
        selected = [row['layout'] for row in report['layouts'] if row['profile'] in ['m06', 'combined']]
        if any(layout != selected[0] for layout in selected):
            raise ValueError('M06/combined layout changed')
        layouts = [row['layout'] for row in report['coroutine_layouts']]
        if any(layout != layouts[0] for layout in layouts):
            raise ValueError('Complete Coroutine offsets/size/alignment changed')
        context_layouts = [row['layout'] for row in report['context_layouts']]
        if any(layout != context_layouts[0] for layout in context_layouts):
            raise ValueError('Complete Context offsets/size/alignment changed')
        backend = context_layouts[0]['backend']
        controller = 'src/coroutine/thread_context.cc' if backend == 'thread' else 'src/coroutine/context.cc'
        required = {'swr_v1_context_prepare', 'swr_v1_context_finish'}
        if backend != 'thread':
            required |= {'swr_v1_context_extent_new', 'swr_v1_context_stack_step', 'swr_v1_context_stack_read'}
        for row in report['commands']:
            if row['profile'] != 'native' and row['unit'] == controller and not required.issubset(row['context_imports']):
                raise ValueError('Actual complete Context controller missed owned bookkeeping')
        if any(sha(path) != digest for path, digest in identities.items()):
            raise ValueError('Owned source changed during check')
        report['passed'] = len(report['commands']) == 30 and len(report['layouts']) == 8 and len(layouts) == 8 and len(context_layouts) == 8
    except Exception as error:
        report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
