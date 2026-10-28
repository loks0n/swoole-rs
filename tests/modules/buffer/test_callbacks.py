"""C++ exceptions thrown by Buffer destroy callbacks terminate the same way with and without Rust."""
from pathlib import Path

import pytest

from native import INCLUDES, LINK, build_and_run
from tools.build_hybrid import hybrid_tree
from tools.harness import run_isolated


@pytest.mark.parametrize('variant', ['upstream', 'rust'])
def test_callback_exception(pinned, archive, variant):
    tree = pinned('include', 'src/core/buffer.cc')
    if variant == 'rust':
        source, flags = hybrid_tree(archive)
        command = ['c++', '-std=c++17', '-O1', '-g', *flags, source / 'src/core/buffer.cc',
                   Path(__file__).with_name('callback-exception.cc'), archive]
    else:
        command = ['c++', '-std=c++17', '-O1', '-g', '-I' + str(tree / 'include'), *INCLUDES,
                   tree / 'src/core/buffer.cc', Path(__file__).with_name('callback-exception.cc')]
    binary = tree / variant
    build_and_run(command + LINK[1:], binary, 'data', timeout=5)
    for case in ['data', 'native', 'teardown']:
        result = run_isolated([str(binary), case], timeout=5)
        assert result.returncode == 77, f'{case}: {result.returncode} {result.stderr}'
