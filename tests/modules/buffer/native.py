"""Shared steps of the native buffer gates: compile against the pinned tree or the hybrid build's tree, run."""
import json
import sys

from tools.build_hybrid import hybrid_tree
from tools.harness import ROOT, run_compiler, run_isolated

SOURCE = ROOT / 'target/upstream/src'
INCLUDES = ['-I' + str(ROOT / 'native/include'), '-I' + str(ROOT / 'native/buffer')]
LINK = ['-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lm'] + (
    ['-ldl', '-lpthread', '-lrt', '-lutil'] if sys.platform.startswith('linux') else [])
SANITIZE = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']


def untyped_hybrid(archive):
    """The hybrid build's tree and flags with SWOOLE_RS_BUFFER_TYPED off. Builds with the Rust
    reactor turn the typed queue on, which replaces the legacy Buffer API (front() rejects every
    call). The legacy-facade fixtures run the same patched sources in the untyped configuration
    that builds without the reactor use; test_typed.py covers the typed one."""
    source, flags = hybrid_tree(archive)
    return source, [flag for flag in flags if flag != '-DSWOOLE_RS_BUFFER_TYPED']


def build_and_run(command, binary, *arguments, timeout=60):
    compiled = run_compiler([*map(str, command), '-o', str(binary)], timeout=60)
    assert compiled['returncode'] == 0, compiled['stderr']
    return run_isolated([str(binary), *arguments], timeout=timeout)


def native_and_selected(tree, test_source, archive, sanitize, *defines):
    """Outcome JSON of one test compiled against pinned buffer.cc, then against the hybrid build's
    buffer.cc and headers with its Rust archive."""
    hybrid, flags = untyped_hybrid(archive)
    outcomes = {}
    for name in ['native', 'selected']:
        headers = ['-I' + str(tree / 'include'), *INCLUDES] if name == 'native' else ['-DSWOOLE_RS_BUFFER', *flags]
        command = ['c++', '-std=c++17', '-O1', '-g', *defines, '-ffunction-sections', '-fdata-sections',
                   *headers, (tree if name == 'native' else hybrid) / 'src/core/buffer.cc', test_source]
        if name == 'selected':
            command.append(archive)
        command += LINK + (SANITIZE if sanitize else [])
        result = build_and_run(command, tree / name)
        assert result.returncode == 0 and not result.stderr, f'{name}: {result.stdout}{result.stderr}'
        outcomes[name] = json.loads(result.stdout)
    return outcomes
