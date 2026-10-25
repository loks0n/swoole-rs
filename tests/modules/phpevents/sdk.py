#!/usr/bin/env python3
"""Compile complete Event TU using a completed immutable PHP-helper SDK capture.

No loading, event operations or original test execution. Each SDK dependency is
verified before reuse; generated config/source/objects remain private.
"""
import argparse
import hashlib
import json
import shlex
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report
from gate import stage


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


EXPORTS = {'swr_v1_phpevents_' + name for name in (
    'alias', 'catalogue', 'fd', 'add', 'stream', 'registry_insert', 'registry_try_insert', 'registry_contains',
    'registry_get', 'registry_erase', 'registry_drop', 'update', 'query',
    'write', 'delete', 'cycle', 'dispatch', 'callbacks', 'update_owned', 'reactor_init', 'handlers', 'loop')}


def check_imports(symbols, feature):
    observed = {line.split()[-1].lstrip('_') for line in symbols.splitlines() if line.split()}
    found = {name for name in observed if name.startswith('swr_v1_phpevents_')}
    if feature == 'native':
        if found:
            raise ValueError('Native profile unexpectedly imports Rust Event policy')
    elif not (EXPORTS - {'swr_v1_phpevents_update', 'swr_v1_phpevents_alias', 'swr_v1_phpevents_registry_insert'}).issubset(found):
        raise ValueError('Selected Event caller imports missing: ' + ', '.join(sorted((EXPORTS - {'swr_v1_phpevents_update', 'swr_v1_phpevents_alias', 'swr_v1_phpevents_registry_insert'}) - found)))
    return sorted(found)


def configured_native_profile(folder):
    """Retain exact observed production inputs; never relabel the strict profile."""
    export = folder / 'export.json'
    recorded = json.loads(export.read_text())
    observation = recorded['native_compilation_observation']
    identities = {}
    for name in ('Makefile', 'config.h', 'build.log'):
        digest = sha(folder / name)
        if digest != recorded['files'][name]['sha256'] or digest != observation['files_sha256'][name]:
            raise ValueError('Changed Native configured input: ' + name)
        identities[name] = digest
    definitions = [line.split('=', 1)[1].strip() for line in (folder / 'Makefile').read_text().splitlines()
                   if line.startswith('CXXFLAGS =')]
    if len(definitions) != 1 or definitions[0] != observation['make_variables']['CXXFLAGS']:
        raise ValueError('Native CXXFLAGS observation does not match Makefile')
    if '$' in definitions[0] or '\n' in definitions[0]:
        raise ValueError('Unexpanded Native CXXFLAGS cannot qualify this profile')
    flags = shlex.split(definitions[0])
    return dict(scope='Observed Native configured flags/config, with explicit -Werror and per-row C++ standard; not the stricter standalone profile',
        source_ref=recorded['source_ref'], export_path=str(export.resolve()), export_sha256=sha(export),
        files_sha256=identities, cxxflags=definitions[0],
        flags_without_standard=[flag for flag in flags if not flag.startswith('-std=')])


def configured_export(args):
    """Whole Event TU from a copied immutable production SDK, no runtime."""
    from tools.private_copy import copy_private
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Choose a unique receipt')
    work = output.parent / ('phpevents-sdk-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, work=str(work), commands=[], profiles=[],
                  runtime_executed=False, measurement_performed=False,
                  scope='Current full Event TU and owned header; copied frozen production SDK/configured flags, not a new producer-source/runtime claim')
    try:
        exported = json.loads(args.sdk_export.read_text())
        report['sdk_source_ref'] = exported['source_ref']
        report['sdk_export_sha256'] = sha(args.sdk_export)
        for name, item in exported['files'].items():
            if sha(args.sdk_export.parent / name) != item['sha256']:
                raise ValueError('Changed export: ' + name)
        source = (Path(exported['files']['build-manifest.json']['source']).parent / 'src').resolve()
        prefix = (source / '../rust-prefix/include').resolve()
        files = [*sorted(source.glob('*.h')), source / 'Makefile',
                 *sorted((source / 'include').rglob('*.h')),
                 *sorted((source / 'ext-src').rglob('*.h')),
                 *sorted((source / 'thirdparty').rglob('*.h'))]
        before = {str(p): sha(p) for p in files}
        before.update({str(p): sha(p) for p in prefix.rglob('*.h')})
        tree = work / 'sdk'
        for path in files:
            dest = tree / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            copy_private(path, dest)
        shutil.copytree(prefix, work / 'ffi-include', copy_function=copy_private)
        includes = shlex.split(next(line.split('=', 1)[1] for line in (source / 'Makefile').read_text().splitlines() if line.startswith('INCLUDES = ')))
        includes = [part.replace(str(source), str(tree)).replace(str(prefix), str(work / 'ffi-include')) for part in includes]
        flags = shlex.split(next(line.split('=', 1)[1] for line in (source / 'Makefile').read_text().splitlines() if line.startswith('CXXFLAGS = ')))
        report['actual_configured_flags'] = flags
        if not args.native_export:
            raise ValueError('Native/M28-only controls require a separate immutable Native export')
        native_export = json.loads((args.native_export / 'export.json').read_text())
        for name, item in native_export['files'].items():
            if sha(args.native_export / name) != item['sha256']:
                raise ValueError('Changed Native export: ' + name)
        native_source = (Path(native_export['files']['build-manifest.json']['source']).parent / 'src').resolve()
        native_tree = work / 'sdk-native'
        native_files = [*sorted(native_source.glob('*.h')), native_source / 'Makefile',
                        *sorted((native_source / 'include').rglob('*.h')),
                        *sorted((native_source / 'ext-src').rglob('*.h')),
                        *sorted((native_source / 'thirdparty').rglob('*.h'))]
        for path in native_files:
            before[str(path)] = sha(path)
            dest = native_tree / path.relative_to(native_source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            copy_private(path, dest)
        native_includes = shlex.split(next(line.split('=', 1)[1] for line in (native_source / 'Makefile').read_text().splitlines() if line.startswith('INCLUDES = ')))
        native_includes = [part.replace(str(native_source), str(native_tree)) for part in native_includes]
        native_flags = shlex.split(next(line.split('=', 1)[1] for line in (native_source / 'Makefile').read_text().splitlines() if line.startswith('CXXFLAGS = ')))
        report['native_sdk_source_ref'] = native_export['source_ref']
        selected_tree, selected_flags, selected_includes = tree, flags, includes
        original, selected = stage(args.source, work / 'overlay')
        configurations = {'native': (native_tree / 'config.h').read_text(), 'combined': (selected_tree / 'config.h').read_text()}
        for feature in ('native', 'phpevents-only', 'combined'):
            for sockets in (False, True):
                for standard in ('c++14', 'c++17'):
                    row = dict(feature=feature, sockets=sockets, standard=standard, status='NOTRUN')
                    report['profiles'].append(row)
        for row in report['profiles']:
            feature, sockets, standard = (row[key] for key in ('feature', 'sockets', 'standard'))
            tree, flags, includes = (selected_tree, selected_flags, selected_includes) if feature == 'combined' else (native_tree, native_flags, native_includes)
            selected_config = configurations['combined' if feature == 'combined' else 'native']
            selected_config += '\n#undef SWOOLE_RS_PHPEVENTS\n#undef SW_SOCKETS\n#undef SWOOLE_SOCKETS_SUPPORT\n'
            if feature != 'native':
                selected_config += '#define SWOOLE_RS_PHPEVENTS 1\n'
            if sockets:
                selected_config += '#define SW_SOCKETS 1\n'
            (tree / 'config.h').write_text(selected_config)
            unit = tree / 'ext-src/swoole_event.cc'
            unit.write_text(original if feature == 'native' else selected)
            obj = work / (feature + '-' + standard + '-' + str(sockets) + '.o')
            command = ['c++', *flags, '-std=' + standard, '-Werror', '-fPIC', '-DENABLE_PHP_SWOOLE', '-DZEND_COMPILE_DL_EXT=1', '-DHAVE_CONFIG_H', '-I' + str(ROOT / 'native/phpevents'), *includes, '-MMD', '-MF', str(obj) + '.d', '-c', str(unit), '-o', str(obj)]
            require_build_space(work)
            result = run_isolated(command, cwd=tree, timeout=120)
            row.update(status='FAILED', command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
            report['commands'].append(row)
            write_report(output, report)
            if result.returncode or result.stderr:
                raise ValueError('Complete configured Event TU failed or warned')
            symbols = run_isolated(['nm', '-u', str(obj)], timeout=30)
            if symbols.returncode:
                raise ValueError('Actual import observation failed')
            row['phpevents_imports'] = check_imports(symbols.stdout, feature)
            deps = shlex.split(Path(str(obj) + '.d').read_text().replace('\\\n', ' ').split(':', 1)[1])
            deps = [(Path(name) if Path(name).is_absolute() else tree / name).resolve() for name in deps]
            header = (ROOT / 'native/phpevents/swoole_rs_phpevents.h').resolve()
            if feature != 'native' and header not in deps:
                raise ValueError('Compiler bypassed current owned Event header')
            row.update(status='PASS')
        if any(sha(path) != value for path, value in before.items()):
            raise ValueError('Borrowed SDK input changed')
        if sha(args.sdk_export) != report['sdk_export_sha256']:
            raise ValueError('SDK export changed')
        report.update(passed=True, borrowed_inputs_before_after_equal=True)
    except Exception as error:
        report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'error', 'work')}))
    return int(not report['passed'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    sdk_input = parser.add_mutually_exclusive_group(required=True)
    sdk_input.add_argument('--sdk-report', type=Path)
    sdk_input.add_argument('--sdk-export', type=Path, help='Immutable export.json with source SDK available read-only')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-export', type=Path, help='Verified immutable Native configured flags/config; distinct from strict default profile')
    args = parser.parse_args()
    if args.sdk_export:
        return configured_export(args)
    output = args.output.resolve()
    work = output.parent / ('phpevents-sdk-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, work=str(work), commands=[], scope=__doc__,
                  runtime_executed=False,
                  measurement_performed=False, limits=[
                      'Compiler qualification only; no Event runtime, originals or lifetime proof.',
                      'Captured native/M26 SDK headers; no newly built combined PHP world.'])
    try:
        native_profile = configured_native_profile(args.native_export) if args.native_export else None
        report['native_configured_profile'] = native_profile
        sdk = json.loads(args.sdk_report.read_text())
        if not sdk['passed'] or not sdk['layout_matched']:
            raise ValueError('SDK prerequisite did not pass')
        original, selected = stage(args.source, work / 'overlay')
        original_rows = [row for row in sdk['commands']
                         if row['unit'] == 'ext-src/php_swoole_cxx.cc'
                         and not row['stdext_enabled'] and row['engine'] in ('native', 'combined')]
        if {(r['engine'], r['cpp_standard']) for r in original_rows} != {
                (e, c) for e in ('native', 'combined') for c in ('c++14', 'c++17')}:
            raise ValueError('Incomplete SDK profile prerequisite')
        dependencies = {}
        for row in original_rows:
            for name, digest in row['dependencies_sha256'].items():
                if sha(name) != digest:
                    raise ValueError('Changed captured SDK dependency: ' + name)
                dependencies[name] = digest
        for feature in ('native', 'phpevents-only', 'combined'):
            for sockets in (False, True):
                profile = work / (feature + '-sockets-' + str(sockets))
                profile.mkdir()
                source = profile / 'swoole_event.cc'
                source.write_text(original if feature == 'native' else selected)
                for standard in ('c++14', 'c++17'):
                    row = next(r for r in original_rows if r['engine'] == (
                        'combined' if feature == 'combined' else 'native')
                        and r['cpp_standard'] == standard)
                    configs = [Path(name) for name, digest in row['dependencies_sha256'].items()
                               if Path(name).name == 'config.h' and digest == row['config_sha256']]
                    if len(configs) != 1:
                        raise ValueError('Ambiguous captured configuration')
                    config = configs[0]
                    (profile / 'config.h').write_text((args.native_export / 'config.h' if native_profile else config).read_text() +
                        '\n#undef SWOOLE_RS_PHPEVENTS\n#undef SW_SOCKETS\n#undef SWOOLE_SOCKETS_SUPPORT\n' +
                        ('#define SWOOLE_RS_PHPEVENTS 1\n' if feature != 'native' else '') +
                        ('#define SW_SOCKETS 1\n' if sockets else ''))
                    shutil.copyfile(config.parent / 'php_swoole.h', profile / 'php_swoole.h')
                    dep = profile / (standard + '.d')
                    obj = profile / (standard + '.o')
                    command = list(row['command'])
                    command[command.index('-fsyntax-only')] = '-c'
                    command[command.index('-MF') + 1] = str(dep)
                    command[-1] = str(source)
                    old_include = '-I' + str(config.parent)
                    command[command.index(old_include)] = '-I' + str(profile)
                    command += (native_profile['flags_without_standard'] + ['-std=' + standard, '-Werror'] if native_profile else ['-O2', '-Wall', '-Werror'])
                    command += ['-I' + str(ROOT / 'native/phpevents'), '-o', str(obj)]
                    require_build_space(ROOT)
                    result = run_isolated(command, timeout=120)
                    entry = dict(feature=feature, sockets=sockets, standard=standard,
                                 command=command, exit=result.returncode, stdout=result.stdout,
                                 stderr=result.stderr)
                    report['commands'].append(entry)
                    write_report(output, report)
                    if result.returncode:
                        raise ValueError('Complete Event TU compilation failed')
                    symbols = run_isolated(['nm', '-u', str(obj)], timeout=30)
                    entry['undefined_symbols'] = dict(exit=symbols.returncode,
                                                       stdout=symbols.stdout, stderr=symbols.stderr)
                    if symbols.returncode:
                        raise ValueError('Object import observation failed')
                    entry['phpevents_imports'] = check_imports(symbols.stdout, feature)
        if any(sha(name) != digest for name, digest in dependencies.items()):
            raise ValueError('Captured SDK changed during compilation')
        if native_profile and configured_native_profile(args.native_export) != native_profile:
            raise ValueError('Native configured inputs changed during compilation')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'error', 'work')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
