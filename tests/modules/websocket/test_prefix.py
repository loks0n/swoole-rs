"""Compare header prefixes against the actual unchanged pinned C++ parser. The Rust side's
declarations come from the hybrid build the archive belongs to."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

import pytest

from tools.build_hybrid import hybrid_tree
from tools.harness import ROOT, run_isolated
from tools.harness import run_compiler

from tools.build_upstream import COMMIT as PIN


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_prefix(pytestconfig, tmp_path):
    if not pytestconfig.getoption('manifest'):
        pytest.skip('needs --manifest')
    source_tree = ROOT / 'target/upstream/src'
    manifest = json.loads(Path(pytestconfig.getoption('manifest')).read_text())
    assert manifest['inputs']['upstream_commit'] == PIN and manifest['migrated_feature_bits'] & 1, \
        'Selected build must enable the WebSocket kernel at the pinned commit'
    prefix = next(value.partition('=')[2] for value in manifest['configure'] if value.startswith('--with-swoole-rs='))
    archive = (Path(prefix) / 'lib/libswoole_rs_ffi.a').resolve(strict=True)
    assert sha(archive) == manifest['inputs']['rust_archive_sha256'], 'Selected archive checksum differs from its build manifest'
    hybrid, flags = hybrid_tree(archive)
    rust_headers = [flag for flag in flags if flag.startswith('-I') and flag != '-I' + str(hybrid / 'include')]
    local = Path(__file__).resolve().parent
    tree = tmp_path
    data = subprocess.check_output(['git', '-C', str(source_tree), 'archive', PIN,
                                    'include', 'thirdparty', 'src/protocol/websocket.cc', 'src/protocol/base.cc'])
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        for member in bundle:
            if member.isfile():
                destination = tree / member.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(bundle.extractfile(member).read())
    binary = tree / 'prefix'
    includes = shlex.split(os.environ.get('CPPFLAGS', ''))
    openssl = next((value.partition('=')[2] for value in manifest['configure'] if value.startswith('--with-openssl-dir=')), None)
    if openssl:
        includes += ['-I' + str(Path(openssl) / 'include')]
    command = shlex.split(os.environ.get('CXX', 'c++')) + includes + [
        '-std=c++17', '-O1', '-g', '-ffunction-sections', '-fdata-sections',
        '-I' + str(tree / 'include'), '-I' + str(tree / 'thirdparty'), *rust_headers,
        str(tree / 'src/protocol/websocket.cc'), str(tree / 'src/protocol/base.cc'), str(local / 'prefix.cc'), str(archive),
        '-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lc', '-lm']
    if sys.platform.startswith('linux'):
        command += ['-ldl', '-lpthread', '-lrt', '-lutil']
    if pytestconfig.getoption('sanitize'):
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    compiled = run_compiler(command + ['-o', str(binary)], timeout=60)
    assert compiled['returncode'] == 0, compiled['stderr']
    result = run_isolated([str(binary)], timeout=15)
    assert result.returncode == 0, result.stderr
    json.loads(result.stdout)
