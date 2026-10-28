"""Build a String consumer against the pinned String sources, upstream or with the
buffer string-storage patch and the Rust archive."""
import io
import re
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

from tools.build_upstream import COMMIT
from tools.harness import ROOT, run_isolated

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from staging import apply_module_patch  # noqa: E402

PATCH = ROOT / 'migration/patches/buffer/0003-string-storage.patch'
SOURCES = ['src/core/string.cc', 'src/core/base.cc', 'src/os/base.cc', 'src/core/base64.cc']


def pinned_tree(source, tree):
    """Extract the pinned String sources and the original string.cpp tests into tree."""
    data = subprocess.check_output(['git', '-C', str(source), 'archive', COMMIT, 'include', *SOURCES])
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        for member in bundle:
            if member.isfile():
                path = tree / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bundle.extractfile(member).read())
    tests = tree / 'string.cpp'
    tests.write_bytes(subprocess.check_output(['git', '-C', str(source), 'show', COMMIT + ':core-tests/src/core/string.cpp']))
    return tests


def original_ids(tests):
    return ['.'.join(match) for match in re.findall(r'^TEST\(\s*(\w+)\s*,\s*(\w+)\s*\)', tests.read_text(), re.MULTILINE)]


def build(tree, engine, consumer, binary, archive=None, *, sanitize=False, optimize=False, extra=()):
    """Compile consumer (a file under this directory) for engine 'upstream' or 'rust'; the
    rust build patches tree first. Returns the compiler result."""
    if engine == 'rust':
        apply_module_patch(tree, PATCH, allow_override=True)
    command = ['c++', '-std=c++17', '-O3' if optimize else '-O1', '-g', '-ffunction-sections', '-fdata-sections',
               '-I' + str(HERE), '-I' + str(tree / 'include'), '-I' + str(ROOT / 'native/buffer'),
               *[str(tree / name) for name in SOURCES], *map(str, extra), str(HERE / consumer)]
    command += shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'openssl'], text=True))
    if engine == 'rust':
        command += ['-DSWR_STRING_RUST_GATE', str(archive)]
    command += ['-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lm']
    if sys.platform.startswith('linux'):
        command += ['-ldl', '-lpthread', '-lrt', '-lutil']
    if sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    return run_isolated([*command, '-o', str(binary)], timeout=60)
