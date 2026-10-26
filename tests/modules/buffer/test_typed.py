"""Typed queue/facade positive source gate; no Socket/network or callback probes."""
import json

import pytest

from native import INCLUDES, LINK, build_and_run, patch
from tools.harness import ROOT


@pytest.mark.parametrize('standard', ['c++14', 'c++17', 'c++20'])
def test_typed(pinned, archive, pytestconfig, standard):
    tree = pinned('include', 'src/core/buffer.cc')
    patch(tree, 2)
    command = ['c++', '-std=' + standard, '-O1', '-g', '-DSWOOLE_RS_BUFFER=1', '-DSWOOLE_RS_BUFFER_TYPED=1',
               '-I' + str(tree / 'include'), *INCLUDES, tree / 'src/core/buffer.cc',
               ROOT / 'tests/modules/buffer/typed.cc', archive, '-lpthread', *LINK[1:]]
    if pytestconfig.getoption('sanitize'):
        command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    result = build_and_run(command, tree / standard)
    assert result.returncode == 0, result.stderr
    json.loads(result.stdout)
