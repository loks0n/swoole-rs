"""Ordinary public String operations, original versus selected, with an exact positive
assertion count: append/write/i32/repeat/copy/termination/reduce, no POP, lifetime,
fault or custom-allocator effects."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from tools.build_hybrid import apply_patch_verified
from tools.harness import ROOT, run_compiler, run_isolated

LAYOUT = '''#include "swoole_rs_string.h"
_Static_assert(sizeof(swr_v1_string_compat_cursor)==80,"cursor");
_Static_assert(offsetof(swr_v1_string_compat_cursor,digits)==68,"digits");
_Static_assert(sizeof(swr_v1_string_compat_step_result)==56,"step");
_Static_assert(offsetof(swr_v1_string_compat_step_result,mask)==52,"mask");
'''
SOURCES = ['src/core/string.cc', 'src/core/base.cc', 'src/os/base.cc', 'src/core/base64.cc']


def test_layout(tmp_path):
    (tmp_path / 'layout.c').write_text(LAYOUT)
    result = run_isolated(['cc', '-std=c11', '-Werror', '-fsyntax-only', '-I' + str(ROOT / 'native/buffer'),
                           str(tmp_path / 'layout.c')], timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('variant', ['original', 'selected'])
def test_compatibility(pinned, request, pytestconfig, variant):
    archive = request.getfixturevalue('archive') if variant == 'selected' else None
    work = pinned('include', *SOURCES)
    openssl = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'openssl'], text=True))
    if variant == 'selected':
        manifest = ROOT / 'migration/patches/buffer/manifest.json'
        entry = json.loads(manifest.read_text())['patches'][2]
        apply_patch_verified(work, manifest.parent / entry['path'], entry['upstream_paths'], entry['sha256'])
    command = ['c++', '-std=c++17', '-O1', '-g', '-ffunction-sections', '-fdata-sections',
               '-I' + str(work / 'include'), '-I' + str(ROOT / 'native/buffer'),
               *[str(work / name) for name in SOURCES], str(Path(__file__).with_name('compatibility.cc')), *openssl]
    if variant == 'selected':
        command.append(str(archive))
    command += ['-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lm']
    if sys.platform.startswith('linux'):
        command += ['-ldl', '-lpthread', '-lrt', '-lutil']
    if pytestconfig.getoption('sanitize'):
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    binary = work / variant
    compiled = run_compiler(command + ['-o', str(binary)])
    assert compiled['returncode'] == 0, compiled['stderr']
    result = run_isolated([str(binary)], timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {'checks': 44, 'profile': 'ordinary-no-custom-no-pop'}
    if variant == 'selected':
        assert 'swr_v1_string_compat_step' in subprocess.check_output(['nm', '-g', str(binary)], text=True)
        for standard in ['c++14', 'c++17', 'c++20']:
            syntax = run_isolated(['c++', '-std=' + standard, '-fsyntax-only', '-I' + str(work / 'include'),
                                   '-I' + str(ROOT / 'native/buffer'),
                                   *shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True)),
                                   str(work / 'src/core/string.cc'), '-O2', '-fstrict-aliasing'], timeout=30)
            assert syntax.returncode == 0, f'{standard}: {syntax.stderr}'
