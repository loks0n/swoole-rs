"""Pinned buffer.cc, string.cc and the original core-test Buffer assertions with the
Buffer patches and the selected Rust archive (--manifest), or a supplied --archive."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from native import INCLUDES, SOURCE, build_and_run, patch
from tools.build_upstream import COMMIT


def selected_archive(pytestconfig):
    if pytestconfig.getoption('manifest'):
        manifest = json.loads(Path(pytestconfig.getoption('manifest')).read_text())
        assert 'buffer' in manifest['inputs']['modules'], 'Build manifest does not enable buffer'
        prefix = next(value.partition('=')[2] for value in manifest['configure'] if value.startswith('--with-swoole-rs='))
        archive = (Path(prefix) / 'lib/libswoole_rs_ffi.a').resolve(strict=True)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['inputs']['rust_archive_sha256'], \
            'Build archive hash does not match manifest'
        return archive
    if pytestconfig.getoption('archive'):
        return Path(pytestconfig.getoption('archive')).resolve(strict=True)
    pytest.skip('needs --manifest or --archive')


def test_native(pinned, pytestconfig):
    archive = selected_archive(pytestconfig)
    sanitize = pytestconfig.getoption('sanitize')
    if pytestconfig.getoption('rust_asan'):
        assert sanitize, 'Rust ASan archive requires the native sanitizer runtime'
        assert '__asan_report_' in subprocess.run(['nm', '-u', str(archive)], capture_output=True, text=True).stdout, \
            'Selected archive lacks Rust ASan report imports'
    tree = pinned('include', 'src/core/buffer.cc', 'src/core/string.cc')
    original = tree / 'core-tests/src/memory/buffer.cpp'
    original.parent.mkdir(parents=True)
    original.write_bytes(subprocess.check_output(['git', '-C', str(SOURCE), 'show', f'{COMMIT}:core-tests/src/memory/buffer.cpp']))
    patch(tree, 2)
    local = Path(__file__).resolve().parent
    command = shlex.split(os.environ.get('CXX', 'c++')) + [
        '-std=c++17', '-O1', '-g', '-ffunction-sections', '-fdata-sections', '-DSWOOLE_RS_BUFFER',
        '-I' + str(local), '-I' + str(tree / 'include'), *INCLUDES,
        str(tree / 'src/core/buffer.cc'), str(tree / 'src/core/string.cc'), str(original), str(local / 'hybrid.cc'), str(archive),
        '-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lc', '-lm']
    command += ['-Dswr_v1_buffer_' + name + '=swr_test_buffer_' + name
                for name in ['append', 'stats', 'front', 'pop', 'front_plan', 'advance']]
    if sys.platform == 'linux':
        command += ['-ldl', '-lpthread', '-lrt', '-lutil']
    if sanitize:
        command.append('-fsanitize=address,undefined')
    result = build_and_run(command, tree / 'hybrid', timeout=20)
    assert result.returncode == 0, result.stderr
    json.loads(result.stdout)
