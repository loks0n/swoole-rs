"""Compile and run the native ABI checks against a feature-enabled archive."""
import os
from pathlib import Path
import shlex

import pytest

from tools.harness import ROOT, run_compiler, run_isolated


def test_kernel(pytestconfig, tmp_path):
    if not pytestconfig.getoption('archive'):
        pytest.skip('needs --archive')
    archive = Path(pytestconfig.getoption('archive')).resolve(strict=True)
    binary = tmp_path / 'kernel'
    command = shlex.split(os.environ.get('CXX', 'c++')) + [
        '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'native/include'),
        str(Path(__file__).with_name('kernel.cc')), str(archive)]
    if pytestconfig.getoption('sanitize'):
        command.append('-fsanitize=address,undefined')
    # rustc --print native-static-libs for the supported hosts. The compiler
    # driver supplies macOS libSystem; Linux also needs libdl and pthread.
    command += ['-lc', '-lm']
    if os.uname().sysname == 'Linux':
        command += ['-ldl', '-lpthread', '-lrt', '-lutil']
    compiled = run_compiler(command + ['-o', str(binary)])
    assert compiled['returncode'] == 0, compiled['stderr']
    result = run_isolated([str(binary)], timeout=15)
    assert result.returncode == 0, result.stderr
