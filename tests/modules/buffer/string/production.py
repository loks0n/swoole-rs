#!/usr/bin/env python3
"""Positive-length loaded String consumer supplement; broader empty-input profile remains failed."""
import argparse
import io
import hashlib
import re
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tools.harness import ROOT, Engine, parse_engines, run_isolated, write_report
from tools.hybrid_identity import attest, sha
from tools.build_upstream import COMMIT, require_build_space

METHODS = {'compatibility': ['_ZN6swoole6String6appendEPKcm','_ZN6swoole6String6repeatEPKcmm','_ZN6swoole6String4copyERKS0_','_ZN6swoole6String6appendEi'], 'format': ['_ZN6swoole6String5allocEmPKNS_9AllocatorE', '_ZN6swoole6String7reserveEm'], 'allocation': ['_ZN6swoole6String5allocEmPKNS_9AllocatorE', '_ZN6swoole6String7reserveEm'], 'ownership': ['_ZN6swoole6StringaSERKS0_', '_ZN6swoole6StringaSEOS0_'], 'integer': ['_ZN6swoole6String6appendEi'], 'split': ['_ZN6swoole6String5splitEPKcmRKNSt3__18functionIFbS2_mEEE' if sys.platform == 'darwin' else '_ZN6swoole6String5splitEPKcmRKSt8functionIFbS2_mEE'],
           'copy': ['_ZN6swoole6String4copyERKS0_', '_ZN6swoole6StringaSERKS0_'],
           'facade': ['_ZN6swoole6Buffer3popEv', '_ZN6swoole6BufferD1Ev'],
           'random': ['_ZN6swoole6String19append_random_bytesEmb'],
           'storage': ['_ZN6swoole6Buffer6appendEPKcj', '_ZN6swoole6String6appendEPKcm'],
           'metadata': ['_ZN6swoole6String7releaseEv', '_ZN6swoole6String4moveEOS0_'],
           'terminator': ['_ZN6swoole6String6appendEPKcm'],
           'iovec': ['_ZN6swoole6Buffer6appendEPK5iovecm' + ('x' if sys.platform == 'darwin' else 'l')]}
PROFILES = {'compatibility':'ordinary-whole-edit-compatibility-supplement', 'format': 'whole-positive-format-workflow-supplement', 'allocation': 'positive-allocation-phase-supplement', 'ownership': 'positive-live-metadata-ownership-supplement', 'integer': 'positive-integer-storage-supplement', 'split': 'positive-split-continuation-supplement', 'copy': 'positive-copy-provenance-supplement', 'facade': 'supported-facade-lifecycle-supplement', 'random': 'positive-length-supplement', 'storage': 'ordinary-storage-supplement',
            'metadata': 'positive-ownership-supplement', 'terminator': 'positive-terminator-supplement',
            'iovec': 'positive-actual-posix-vector-supplement'}
CASES = {'compatibility':['bytes_append','object_append','write','integer','multibyte_repeat','singlebyte_repeat','copy','termination','reduce'], 'format': ['all_append_grow_flags','exact_capacity_output','empty_sizing','binary_output','caught_reserve_oom','offset_effect'], 'allocation': ['initial_metadata_before_malloc','reserve_offset_effect','reserve_oom_prefix','default_initialization'], 'ownership': ['copy_live_metadata','move_live_metadata','self_assignment','destructor_live_metadata','native_owner_cleanup'], 'integer': ['signed_limits','positive_zero_negative','spare_full_storage','exact_custom_allocation','caught_realloc_failure'], 'split': ['false_throw_offsets','callback_reallocation','future_byte_mutation','offset_side_effect','binary_residual'],
         'copy': ['binary_copy','independent_owners','assignment_effect_prefix','self_assignment','constructor_oom','borrowed_source'],
         'facade': ['cached_identity_offset','positive_data_pop','close_token_callback','mixed_destructor_drain'],
         'random': [dict(encoded=e, requested=n) for e in [False, True] for n in [1,2,3,4,7,16,63,1024]],
         'storage': ['string_edits','copy_move','format','split','buffer_append_drain','positive_vector'],
         'metadata': ['clear','move','release','move_assignment','self_assignment','positive_capacity'],
         'terminator': ['owned_spare','owned_full','borrowed_spare','text_constructor','binary_constructor'],
         'iovec': [dict(count=n, chunk=c, offset=0) for n in [1,8,9,32] for c in [0,1,4]]}



def consumer_inventory(consumer, result, selected):
    origins = {'compatibility':1,'format':2,'allocation':1,'ownership':2,'facade':3,'copy':2,'split':1,'integer':2}
    return (consumer != 'compatibility' or result.get('checks') == 44) and (consumer != 'format' or result.get('checks') == 604) and (consumer != 'allocation' or result.get('checks') == 12) and (consumer != 'ownership' or result.get('checks') == 13) and (consumer not in origins or
        result.get('selected_origin_checks') == (origins[consumer] if selected else 0))


def compatibility_inputs(manifest):
    """Reject older producer inputs before any PHP/DSO/addon execution."""
    name='crates/buffer/src/string/compatibility.rs'
    digest=manifest.get('inputs',{}).get('rust_sources_sha256',{}).get(name)
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Compatibility requires concrete new continuation source; older producers are not qualified')
    return dict(path=name,sha256=digest,scope='Required source presence only; full source/archive/DSO attestation and actual method/origins still mandatory')



def direct_fields_inputs(manifest, selected_export, native_export, source_ref, required, consumer):
    """Fail closed on mode/source/config before any PHP/DSO/addon execution."""
    key='string_direct_fields_requested'
    requested=manifest.get('inputs',{}).get(key,False)
    if not isinstance(requested,bool):
        raise ValueError('Direct fields requested identity must be boolean')
    if not required and not requested:
        return None
    if not required or not requested:
        raise ValueError('Direct fields requires literal --require-direct-fields and requested=true')
    if consumer != 'compatibility':
        raise ValueError('Only exact44 compatibility consumer is qualified for direct-mode readiness')
    if not re.fullmatch('[0-9a-f]{40}',source_ref):
        raise ValueError('Direct fields requires literal source SHA')
    sources={}
    for path, table in [('crates/buffer/src/string/fields.rs','rust_sources_sha256'),
                        ('native/buffer/swoole_rs_string_fields.h','headers_sha256')]:
        value=manifest.get('inputs',{}).get(table,{}).get(path)
        if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
            raise ValueError('Direct fields requires concrete source identity: '+path)
        raw=subprocess.check_output(['git','show',source_ref+':'+path],cwd=ROOT)
        if hashlib.sha256(raw).hexdigest()!=value:
            raise ValueError('Direct field source differs from compiled manifest: '+path)
        sources[path]=value
    path='migration/patches/buffer/0003-string-storage.patch'
    entries=[entry for entry in manifest.get('inputs',{}).get('patches',[]) if entry.get('path')==path]
    if len(entries)!=1 or set(entries[0].get('upstream_paths',[]))!={'src/core/string.cc','include/swoole_string.h'}:
        raise ValueError('Direct fields requires exact actual String caller overlay')
    raw=subprocess.check_output(['git','show',source_ref+':'+path],cwd=ROOT)
    if hashlib.sha256(raw).hexdigest()!=entries[0].get('sha256'):
        raise ValueError('Direct field caller overlay differs from compiled source')
    sources[path]=entries[0]['sha256']
    configs=[]
    for selected, export_path in [(True,selected_export),(False,native_export)]:
        export=json.loads(export_path.read_text())
        for name in ['config.h','build-manifest.json','swoole.so']:
            if sha(export_path.parent/name)!=export.get('files',{}).get(name,{}).get('sha256'):
                raise ValueError('Direct field export input changed: '+name)
        data=json.loads((export_path.parent/'build-manifest.json').read_text())
        actual=data.get('inputs',{}).get(key,False)
        if actual is not selected:
            raise ValueError('Direct fields requires selected ON and Native OFF manifests')
        if selected and (export.get('source_ref')!=source_ref or data!=manifest):
            raise ValueError('Direct fields selected export does not bind exact source/manifest')
        raw=(export_path.parent/'config.h').read_text()
        values=re.findall(r'^\s*#\s*define\s+SWOOLE_RS_STRING_DIRECT_FIELDS(?:[ \t]+([^\r\n]+))?$',raw,re.MULTILINE)
        undef=re.findall(r'^\s*#\s*undef\s+SWOOLE_RS_STRING_DIRECT_FIELDS\b',raw,re.MULTILINE)
        if len(values)>1 or (values and undef) or any(value.strip() not in ['0','1'] for value in values):
            raise ValueError('Direct fields actual SDK macro is ambiguous or unsupported')
        enabled=bool(values and values[0].strip()=='1')
        if enabled is not selected:
            raise ValueError('Direct fields actual SDK macro does not match selected/Native mode')
        configs.append(dict(selected=selected,source_ref=export.get('source_ref'),actual_macro=1 if enabled else 0))
    return dict(sources=sources,configs=configs,scope='Source/config admission only; actual ABI, methods, addon imports and loaded origins remain mandatory')


def headers(source, export_path, manifest, destination):
    export = json.loads(export_path.read_text())
    def git(path):
        return subprocess.check_output(['git', 'show', export['source_ref'] + ':' + path], cwd=ROOT)
    for name in ['config.h', 'build-manifest.json', 'swoole.so']:
        if sha(export_path.parent / name) != export['files'][name]['sha256']:
            raise ValueError('Export input changed: ' + name)
    if sha(export_path.parent / 'build-manifest.json') != sha(manifest):
        raise ValueError('Export does not identify the actual manifest')
    data = json.loads(manifest.read_text())
    if data['inputs']['upstream_commit'] != COMMIT:
        raise ValueError('Native source pin differs')
    destination.mkdir()
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', COMMIT, 'include'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            path = Path(member.name)
            if not member.isfile():
                continue
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Invalid pinned header path')
            output = destination / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(tar.extractfile(member).read())
    # No enclosing Git checkout can silently mask these patch paths.
    subprocess.run(['git', 'init', '-q', str(destination)], check=True)
    for index, entry in enumerate(data['inputs']['patches']):
        paths = [name for name in entry['upstream_paths'] if name.startswith('include/') and Path(name).suffix in ['.h', '.hpp', '.inc']]
        if not paths:
            continue
        patch = destination / ('patch-' + str(index))
        patch.write_bytes(git(entry['path']))
        if sha(patch) != entry['sha256']:
            raise ValueError('Compiled header patch differs from exact source')
        args = ['git', 'apply', *['--include=' + name for name in paths], str(patch)]
        subprocess.run([*args[:2], '--check', *args[2:]], cwd=destination, capture_output=True, check=True)
        subprocess.run(args, cwd=destination, capture_output=True, check=True)
    shutil.copy2(export_path.parent / 'config.h', destination / 'include/config.h')
    seen = set()
    for name, expected in data['inputs']['headers_sha256'].items():
        output = destination / 'include' / Path(name).name
        if output.name in seen:
            raise ValueError('Compiled ABI header basenames collide')
        seen.add(output.name)
        output.write_bytes(git(name))
        if sha(output) != expected:
            raise ValueError('Compiled ABI header differs from exact source')
    return dict(source_ref=export['source_ref'],
                files_sha256={str(path.relative_to(destination)): sha(path) for path in sorted((destination / 'include').rglob('*')) if path.is_file()})


def immutable_export_input(extension, exports):
    """Bind one exact regular export DSO, refusing aliases before PHP is loaded."""
    extension = Path(extension).absolute()
    if extension != extension.resolve():
        raise ValueError('Borrowed extension must be a canonical export path, not an alias')
    matches = []
    for candidate in exports:
        candidate = Path(candidate).absolute()
        if candidate != candidate.resolve():
            raise ValueError('Borrowed export must be a canonical path, not an alias')
        if extension == candidate.parent / 'swoole.so':
            matches.append(candidate)
    if len(matches) != 1:
        raise ValueError('Borrowed extension must be the exact identified export DSO')
    export = matches[0]
    data = json.loads(export.read_text())
    source_ref = data['source_ref']
    if len(source_ref) != 40 or any(c not in '0123456789abcdef' for c in source_ref):
        raise ValueError('Borrowed export needs an exact source commit')
    observed = subprocess.check_output(['git', 'rev-parse', '--verify', source_ref + '^{commit}'], cwd=ROOT, text=True).strip()
    if observed != source_ref:
        raise ValueError('Borrowed export source is unavailable or differs')
    files = data['files']
    if not {'config.h', 'build-manifest.json', 'swoole.so'} <= files.keys():
        raise ValueError('Borrowed export is incomplete')
    bound = {str(export): sha(export)}
    for name, identity in files.items():
        if Path(name).name != name or name in ['.', '..']:
            raise ValueError('Invalid borrowed export member')
        path = export.parent / name
        if path != path.resolve() or not path.is_file() or sha(path) != identity['sha256']:
            raise ValueError('Borrowed export input changed: ' + name)
        bound[str(path)] = identity['sha256']
    manifest = json.loads((export.parent / 'build-manifest.json').read_text())
    if manifest['extension_sha256'] != files['swoole.so']['sha256']:
        raise ValueError('Borrowed manifest does not identify actual extension')
    return dict(mode='borrowed-owner-private-immutable-export', extension=str(extension),
                source_ref=source_ref, export=str(export), before_sha256=bound)


def verify_borrowed_input(binding):
    after = {name: sha(Path(name)) for name in binding['before_sha256']}
    binding['after_sha256'] = after
    if after != binding['before_sha256']:
        raise ValueError('Borrowed immutable export changed during actual consumer run')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--source-ref', required=True)
    p.add_argument('--engine', action='append', required=True)
    p.add_argument('--build-manifest', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--selected-export', type=Path, required=True)
    p.add_argument('--native-export', type=Path, required=True)
    p.add_argument('--php', default='php')
    p.add_argument('--php-config', default='php-config')
    p.add_argument('--php-extension', action='append', default=[])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--consumer', choices=PROFILES, default='random')
    p.add_argument('--require-direct-fields', action='store_true', help='Exact44 only; require actual requested/source/config and selected controller origins')
    p.add_argument('--borrow-immutable-exports', action='store_true', help='Borrow exact canonical owner-private export DSOs after source/hash checks; never mutable aliases')
    a = p.parse_args()
    output = a.output.resolve()
    if output.exists():
        p.error("Unique output path required; preserve initial outcomes")
    work = output.parent / ('string-production-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, assigned_to='@loks0n', work=str(work),
                  require_direct_fields=a.require_direct_fields, profile=PROFILES[a.consumer], cases=CASES[a.consumer], broader_failed_gate_replaced=False, extension_mode='borrowed-immutable-exports' if a.borrow_immutable_exports else 'private-copies', borrowed_inputs=[], commands=[], engines=[], results=[],
                  limits=['Genuine loaded production methods are called; addon includes no String/Buffer implementation or linked Rust archive. Source-qualified inline header bodies remain native/control callers.',
                          'Ordinary entropy/Base64 integration; independent strict/canonical PHP decoding, not an entropy-byte oracle or short-read/OOM/lifetime/performance claim.' if a.consumer == 'random' else 'Positive owned storage/metadata supplement only; no unsafe original domain, complete lifetime/parity or performance claim.'])
    def run(command, timeout=60):
        require_build_space(ROOT)
        require_build_space(work)
        result = run_isolated(list(map(str, command)), timeout=timeout, cwd=work)
        report['commands'].append(dict(command=list(map(str, command)), exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        if result.returncode or result.stderr:
            raise ValueError('Command failed or warned; first outputs retained')
        return result.stdout
    try:
        actual_manifest=json.loads(a.build_manifest.read_text())
        report['direct_fields_source_admission']=direct_fields_inputs(actual_manifest,a.selected_export,
            a.native_export,a.source_ref,a.require_direct_fields,a.consumer)
        if a.consumer == 'compatibility':
            report['compatibility_source_admission']=compatibility_inputs(json.loads(a.build_manifest.read_text()))
        source = Path(__file__).parent
        stem = {'random':'production','compatibility':'compatibility-production','copy':'copy-production','split':'split-production','integer':'integer-production','ownership':'ownership-production','allocation':'allocation-production','format':'format-production'}.get(a.consumer,a.consumer)
        fixture = work / 'production.php'
        fixture.write_bytes((source / (stem + '.php')).read_bytes())
        report['fixture_sha256'] = sha(fixture)
        copies = []
        borrowed = {}
        if a.borrow_immutable_exports:
            for value in a.engine:
                _, separator, raw_extension = value.partition('=')
                if not separator:
                    raise ValueError('Use --engine NAME=/absolute/path/to/extension')
                binding = immutable_export_input(raw_extension, [a.selected_export, a.native_export])
                borrowed[binding['extension']] = binding
                report['borrowed_inputs'].append(binding)
        for index, engine in enumerate(parse_engines(a.engine, a.php, a.php_extension)):
            copied = engine.extension if a.borrow_immutable_exports else work / ('engine-' + str(index) + '.so')
            if a.borrow_immutable_exports:
                verify_borrowed_input(borrowed[str(copied)])
            else:
                shutil.copy2(engine.extension, copied)
                if sha(copied) != sha(engine.extension):
                    raise ValueError('Extension copy differs')
            metadata = json.loads(run(Engine(engine.name, copied, a.php, tuple(a.php_extension)).command('-r',
                "echo json_encode(['php'=>PHP_VERSION,'zts'=>PHP_ZTS,'rust_feature_bits'=>defined('SWOOLE_RS_FEATURE_BITS')?SWOOLE_RS_FEATURE_BITS:0]);")))
            metadata.update(name=engine.name, extension=str(copied), sha256=sha(copied))
            copies.append(metadata)
        if len(copies) != 2 or sum(bool(row['rust_feature_bits'] & 2) for row in copies) != 1:
            raise ValueError('Require native and M01 selected actual pair')
        report['engines'] = copies
        selected = next(row for row in copies if row['rust_feature_bits'] & 2)
        report['source_attestation'] = attest(a.build_manifest, a.archive, selected, a.source_ref, 2)
        php_includes = shlex.split(subprocess.check_output([a.php_config, '--includes'], text=True))
        for row in copies:
            selected = bool(row['rust_feature_bits'] & 2)
            export = a.selected_export if selected else a.native_export
            manifest = a.build_manifest if selected else export.parent / 'build-manifest.json'
            if json.loads(manifest.read_text())['extension_sha256'] != row['sha256']:
                raise ValueError('Build manifest does not identify actual extension')
            mirror = work / (row['name'] + '-headers')
            row['headers'] = headers(a.source, export, manifest, mirror)
            if row['php'] != subprocess.check_output([a.php_config, '--version'], text=True).strip():
                raise ValueError('PHP compile SDK differs from loaded runtime')
            addon = work / (row['name'] + '-addon.so')
            command = ['c++', '-std=c++17', '-O2', '-fPIC', '-shared', '-DHAVE_CONFIG_H',
                       *php_includes, '-I' + str(mirror / 'include'), '-MD', '-MF', str(addon) + '.d', source / (stem + '.cc'), '-o', addon]
            command += ['-undefined', 'dynamic_lookup'] if sys.platform == 'darwin' else ['-ldl']
            run(command)
            dependencies = shlex.split(Path(str(addon) + '.d').read_text().replace('\\\n', ' ').split(':', 1)[1])
            if any(str(a.source.resolve()) in str(Path(name).resolve()) for name in dependencies):
                raise ValueError('Compiler escaped reconstructed header mirror')
            undefined = subprocess.check_output(['nm', '-u', str(addon)], text=True)
            if any(method not in undefined for method in METHODS[a.consumer]):
                raise ValueError('Addon does not require the genuine production method')
            if selected and a.require_direct_fields and '_ZN6swoole6String16initialize_bytesEPKcm' not in undefined:
                raise ValueError('Direct fields addon lacks actual production constructor bridge')
            if selected and a.consumer == 'compatibility' and '_ZN6swoole6String19set_null_terminatedEv' not in undefined:
                raise ValueError('Selected compatibility addon lacks actual outlined termination consumer')
            if selected and a.consumer == 'terminator' and '_ZN6swoole6String19set_null_terminatedEv' not in undefined:
                raise ValueError('Selected terminator addon lacks the actual outlined consumer')
            if selected and a.consumer == 'format' and '_ZNK6swoole6String11format_stepEjimm' not in undefined:
                raise ValueError('Selected formatter addon lacks actual outlined step consumer')
            if selected and a.consumer == 'ownership' and '_ZN6swoole6String7disposeEv' not in undefined:
                raise ValueError('Selected ownership addon lacks actual outlined disposal consumer')
            if selected and a.consumer == 'facade' and '_ZNK6swoole6Buffer5frontEv' not in undefined:
                raise ValueError('Selected facade addon lacks actual outlined front consumer')
            engine = Engine(row['name'], Path(row['extension']), a.php, tuple(a.php_extension))
            result = json.loads(run(engine.command('-d', 'extension=' + str(addon), fixture)))
            if a.consumer=='compatibility' and result.get('direct_fields') is not (selected and a.require_direct_fields):
                raise ValueError('Actual compiled addon direct mode does not match explicit selected/Native admission')
            if not consumer_inventory(a.consumer, result, selected):
                raise ValueError('Actual consumer/origin assertion inventory differs')
            if any(image != str(Path(row['extension']).resolve()) for image in [result['method_image'], *result.get('additional_method_images', {}).values()]):
                raise ValueError('String symbol resolves outside the actual production extension')
            if any(sha(mirror / relative) != digest for relative, digest in row['headers']['files_sha256'].items()):
                raise ValueError('Reconstructed headers changed during actual consumer run')
            report['results'].append(dict(engine=row['name'], passed=True, **result))
            if sha(row['extension']) != row['sha256'] or sha(fixture) != report['fixture_sha256']:
                raise ValueError('Actual consumer inputs changed')
        checks = [row['checks'] for row in report['results']]
        if len(set(checks)) != 1:
            raise ValueError('Native/selected consumer assertion counts differ')
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        if isinstance(error, subprocess.CalledProcessError):
            report['command_error'] = dict(stdout=str(error.stdout), stderr=str(error.stderr))
    for binding in report['borrowed_inputs']:
        try:
            verify_borrowed_input(binding)
        except Exception as error:
            report['passed'] = False
            report.setdefault('borrowed_input_errors', []).append(str(error))
            report.setdefault('error', f'{type(error).__name__}: {error}')
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
