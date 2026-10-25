#!/usr/bin/env python3
"""Positive 24-byte overload contract using exact Native bodies and an immutable production M19 archive."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from gate import PIN, ROOT, body, sha
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--export', dest='export', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-boundary-rng.json')
    args = parser.parse_args()
    directory = args.export.resolve()
    export_path = directory/'export.json'
    export = json.loads(export_path.read_text())
    manifest_path = directory/'build-manifest.json'
    archive = directory/'libswoole_rs_ffi.a'
    report = {'passed': False, 'full_gate_passed': False, 'scope': __doc__, 'pin': PIN,
              'export_source_ref': export['source_ref'],
              'archive_sha256': sha(archive),
              'native_asan_ubsan': True, 'rust_instrumented': False,
              'unrun': ['actual entropy/thread-local RNG initialization', 'allocation/partial/exception/lifetime profiles',
                        'loaded M04/M19 production coupling', 'originals/configuration/default activation/performance']}
    try:
        for name in ['libswoole_rs_ffi.a', 'build-manifest.json']:
            if sha(directory/name) != export['files'][name]['sha256']:
                raise ValueError('Immutable export copy identity differs: '+name)
        inputs = json.loads(manifest_path.read_text())['inputs']
        if inputs['upstream_commit'] != PIN or 'corebase' not in inputs['modules']:
            raise ValueError('Production export does not select pinned corebase')
        if inputs['rust_archive_sha256'] != report['archive_sha256']:
            raise ValueError('Production archive does not match its build inputs')
        header = ROOT/'native/corebase/swoole_rs_corebase.h'
        if sha(header) != inputs['headers_sha256']['native/corebase/swoole_rs_corebase.h']:
            raise ValueError('Current M19 header differs from exact production contract')
        fingerprints = {name: value for name, value in inputs['rust_sources_sha256'].items() if name.startswith('crates/corebase/')}
        if not fingerprints or any(sha(ROOT/name) != value for name, value in fingerprints.items()):
            raise ValueError('Current M19 Rust source differs from production inputs')
        patch = ROOT/'migration/patches/corebase/0001-rust-core-helpers.patch'
        entry = next(p for p in inputs['patches'] if p['path'] == str(patch.relative_to(ROOT)))
        with tempfile.TemporaryDirectory(prefix='swr-http-boundary-rng-') as temporary:
            tree = Path(temporary)
            native = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN+':src/core/base.cc'])
            path = tree/'src/core/base.cc'
            path.parent.mkdir(parents=True)
            path.write_bytes(native)
            report['patch_application'] = apply_patch_verified(tree, patch, entry['upstream_paths'], entry['sha256'])
            selected = path.read_text()
            original = native.decode()
            first = original.index('static constexpr char characters[]')
            characters = original[first:original.index('};', first)+2]
            preamble = '#include "swoole_rs_corebase.h"\n#include <cstdlib>\n#include <string>\n#include <vector>\n#include <utility>\n'
            generated = preamble
            for namespace, source in [('original', original), ('selected', selected)]:
                generated += 'namespace '+namespace+' {\nsize_t seed=0,position=0;std::vector<std::pair<int,int>> draws;\nint swoole_rand(int low,int high){draws.emplace_back(low,high);return (seed+position++)%62;}\n'
                if namespace == 'original': generated += characters+'\n'
                generated += body(source, 'void swoole_random_string(char *buf, size_t len)')+'\n'
                generated += body(source, 'void swoole_random_string(std::string &str, size_t len)')+'\n}\n'
            (tree/'rng_bodies.h').write_text(generated)
            binary = tree/'gate'
            command = ['c++', '-std=c++14', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                       '-I'+str(header.parent), '-I'+str(tree), str(Path(__file__).with_suffix('.cc')), str(archive), '-lm', '-o', str(binary)]
            if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
            report['free_before_compile_bytes'] = require_build_space(tree)
            for label, command in [('compile', command), ('run', [str(binary)])]:
                result = run_isolated(command, timeout=60)
                report[label] = {'command': command, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
                if result.returncode: return 1
            report['outcome'] = json.loads(report['run']['stdout'].splitlines()[-1])
            report['archive_unchanged'] = sha(archive) == report['archive_sha256']
            report['passed'] = report['archive_unchanged']
            print(json.dumps(report['outcome']))
            return 0 if report['passed'] else 1
    except Exception as error:
        report['prerequisite_or_tooling_error'] = str(error)
        return 1
    finally:
        write_report(args.output, report)


if __name__ == '__main__':
    sys.exit(main())
