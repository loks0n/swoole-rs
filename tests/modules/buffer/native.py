"""Shared steps of the native buffer gates: apply the module's patches, compile, run."""
import json
import sys

from staging import apply_module_patch
from tools.harness import ROOT, run_compiler, run_isolated

SOURCE = ROOT / 'target/upstream/src'
PATCHES = ROOT / 'migration/patches/buffer'
INCLUDES = ['-I' + str(ROOT / 'native/include'), '-I' + str(ROOT / 'native/buffer')]
LINK = ['-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lm'] + (
    ['-ldl', '-lpthread', '-lrt', '-lutil'] if sys.platform.startswith('linux') else [])
SANITIZE = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']


def patch(tree, count):
    """Apply the first `count` buffer patches, each checked against the module manifest."""
    for entry in json.loads((PATCHES / 'manifest.json').read_text())['patches'][:count]:
        apply_module_patch(tree, PATCHES / entry['path'])


def build_and_run(command, binary, *arguments, timeout=60):
    compiled = run_compiler([*map(str, command), '-o', str(binary)], timeout=60)
    assert compiled['returncode'] == 0, compiled['stderr']
    return run_isolated([str(binary), *arguments], timeout=timeout)


def native_and_selected(tree, test_source, archive, sanitize, *defines):
    """Outcome JSON of one test compiled against pinned buffer.cc, then with the Buffer patches and Rust."""
    outcomes = {}
    for name in ['native', 'selected']:
        if name == 'selected':
            patch(tree, 2)
        command = ['c++', '-std=c++17', '-O1', '-g', *defines, '-ffunction-sections', '-fdata-sections',
                   '-I' + str(tree / 'include'), *INCLUDES, tree / 'src/core/buffer.cc', test_source]
        if name == 'selected':
            command += ['-DSWOOLE_RS_BUFFER', archive]
        command += LINK + (SANITIZE if sanitize else [])
        result = build_and_run(command, tree / name)
        assert result.returncode == 0 and not result.stderr, f'{name}: {result.stdout}{result.stderr}'
        outcomes[name] = json.loads(result.stdout)
    return outcomes
