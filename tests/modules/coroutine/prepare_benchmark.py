#!/usr/bin/env python3
"""Freeze optimized actual-runtime artifacts; run untimed checksum checks only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
MODES = ['create', 'yield', 'channel', 'cancel', 'fanin']
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--core-build', type=Path, required=True, help='Completed private ordinary, optimized ASM native core pair')
p.add_argument('--output', type=Path, required=True, help='NEW immutable prepared directory; existing directory rejected')
a = p.parse_args()
if a.output.exists():
    p.error('Prepared directory already exists; never replace an immutable artifact')
a.output.mkdir(parents=True)
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
report = {'scope': 'Matched actual native reference/coroutine-only runtime; optimized artifacts. Correctness checks are untimed. No benchmark lease or performance result.',
          'modes': MODES, 'engines': []}
for engine in ['upstream', 'rust']:
    core = (a.core_build / ('core-' + engine)).resolve()
    flags = (core / 'build/CMakeFiles/lib-swoole.dir/flags.make').read_text()
    if '-O2' not in flags or '-fsanitize' in flags or '-UNDEBUG' not in flags:
        raise ValueError('Require optimized ordinary assertion-enabled native core artifacts')
    dest = a.output.resolve() / engine
    dest.mkdir()
    extension = '.dylib' if sys.platform == 'darwin' else '.so'
    library = core / ('lib/libswoole' + extension)
    frozen = dest / ('libswoole' + extension)
    shutil.copy2(library, frozen)
    if sys.platform == 'darwin':
        subprocess.run(['install_name_tool', '-id', '@rpath/libswoole.dylib', str(frozen)], check=True)
        subprocess.run(['codesign', '--force', '--sign', '-', str(frozen)], check=True, capture_output=True)
    else:
        # Match the original SONAME without mutating ELF contents.
        (dest / 'libswoole.so.6.2.2').symlink_to(frozen.name)
    binary = dest / 'benchmark'
    includes = shlex.split(next(line.split('=', 1)[1] for line in flags.splitlines() if line.startswith('CXX_INCLUDES =')))
    native_link = shlex.split((core / 'build/CMakeFiles/core-tests.dir/link.txt').read_text())
    dependencies = [arg for arg in native_link if ((arg.startswith('-L') or arg.startswith('-l')) or arg.endswith(('.a', '.dylib', '.so'))) and not any(name in arg for name in ['swoole', 'gtest', 'gmock'])]
    command = ['c++', '-std=c++14', '-O2', '-UNDEBUG', '-DHAVE_CONFIG_H',
               *includes,
               str(ROOT / 'tests/modules/coroutine/benchmark.cc'), '-L' + str(dest), '-lswoole',
               '-Wl,-rpath,' + str(dest), '-pthread', *dependencies, '-o', str(binary)]
    subprocess.run(command, check=True)
    checks = []
    for mode in MODES:
        run = subprocess.run([str(binary), '--check', mode, '10'], capture_output=True, text=True, timeout=20)
        if run.returncode:
            raise RuntimeError(mode + ': ' + run.stdout + run.stderr)
        row = json.loads(run.stdout)
        if row['checksum'] != 10 or 'nanoseconds' in row:
            raise ValueError('Untimed witness identity differs')
        checks.append(row)
    report['engines'].append({'name': engine, 'source_library': str(library),
                              'published_library': str(frozen), 'published_library_sha256': sha(frozen),
                              'binary': str(binary), 'binary_sha256': sha(binary),
                              'compiler_flags': flags,
                              'command': command, 'native_link_dependencies': dependencies, 'checks': checks})
(a.output / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
print(a.output / 'prepared.json')
