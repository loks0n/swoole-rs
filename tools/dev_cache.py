"""Small Unix build primitives: exclusive writers and dependency-keyed native binaries."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import time

from tools.harness import ROOT, run_isolated, write_report
from tools.private_copy import copy_private


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextlib.contextmanager
def exclusive(path):
    """Fail visibly rather than racing another build or silently waiting on it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f'Another writer holds {path}; retry after it finishes') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


LINK_SUFFIXES = ('.o', '.obj', '.a', '.so', '.dylib', '.rlib', '.lib')


def is_link_file(arg):
    return not arg.startswith('-') and (arg.endswith(LINK_SUFFIXES) or re.search(r'\.so(?:\.[0-9]+)+$', arg))


def unsupported_link_input(command):
    # A conservative miss preserves the real compiler result and original flags.
    safe_link_flags = {'-Wl,-dead_strip', '-Wl,--gc-sections'}
    binary_magic = (b'!<arch>\n', b'\x7fELF', b'BC\xc0\xde', b'\xde\xc0\x17\x0b',
                    b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce',
                    b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')
    skip = False
    for arg in command[1:]:
        if skip:
            skip = False
            continue
        if arg == '-o':
            skip = True
            continue
        if (arg.startswith(('@', '-l', '-L', '-F', '-T', '-Clink', 'link-arg=', 'link-args=', 'linker=',
                            '-fplugin', '-fmodule-file', '--config', '--output', '--out-dir', '-M',
                            '-save-temps', '-gsplit-dwarf', '-fuse-ld', '--ld-path', '-B',
                            '-specs', '--specs', '--gcc-toolchain', '--gcc-install-dir'))
                or arg.startswith('-o')
                or arg in {'-Xlinker', '-Xclang', '-framework', '-weak_framework', '-static',
                           '-static-libgcc', '-static-libstdc++', '-include-pch', '-include-pth'}
                or arg.startswith('-Wl,') and arg not in safe_link_flags):
            return 'untracked linker/response/library input: ' + arg
        if is_link_file(arg):
            try:
                with Path(arg).open('rb') as handle:
                    magic = handle.read(8)
            except OSError:
                return 'unavailable explicit link input: ' + arg
            if not magic.startswith(binary_magic):
                return 'indirect archive/script or unsupported link format: ' + arg
    return None


def compile_cached(command, *, output, scratch, timeout=60, cache=True):
    """Reuse compilation, never outcomes. Discover dependencies through C/C++ or Rust."""
    started = time.monotonic()
    output, scratch = Path(output), Path(scratch)
    command = list(map(str, command))
    key = None
    hit = False
    reason = 'disabled'
    cache = cache and os.environ.get('SWOOLE_RS_NO_CACHE') != '1'
    unsupported = unsupported_link_input(command) if cache else None
    if unsupported:
        cache, reason = False, unsupported + '; compiling without cache'
    driver = []
    for arg in command:
        if arg.startswith('-') or is_link_file(arg) or Path(arg).suffix in {'.c', '.cc', '.cpp', '.cxx', '.rs'}:
            break
        driver.append(arg)
    if cache:
        compiler = Path(shutil.which(command[0]) or command[0]).resolve()
        with compiler.open('rb') as handle:
            scripted_compiler = handle.read(2) == b'#!'
        if (len(driver) != 1 or compiler.name in {'env', 'ccache', 'sccache', 'distcc', 'xcrun'}
                      or scripted_compiler):
            cache, reason = False, 'compiler wrapper/prefix closure is untracked; compiling without cache'
    if cache:
        # Keep preprocessing flags, dropping linker-only arguments and the output.
        dependencies, link_inputs = [], []
        skip = False
        for arg in command:
            if skip:
                skip = False
                continue
            if arg == '-o':
                skip = True
            elif is_link_file(arg):
                link_inputs.append(arg)
            elif not arg.startswith('-Wl,'):
                dependencies.append(arg)
        rust = Path(command[0]).name == 'rustc'
        depfile = scratch / 'rust-dependencies.d'
        probe = run_isolated([*dependencies, *(['--emit=dep-info=' + str(depfile)] if rust else
                                             ['-M', '-MT', 'swr_cache'])], timeout=timeout)
        if probe.returncode == 0 and not rust:
            # Dependency-only preprocessing does not expand volatile builtins. A
            # separate probe substitutes string literals, catching even token-pasted
            # uses without changing the actual compilation or its clock/environment.
            marker = 'SWR_CACHE_VOLATILE_BUILTIN'
            volatile = run_isolated([*dependencies, '-E', '-Wno-builtin-macro-redefined',
                                     *['-D' + name + '="' + marker + '"' for name in
                                       ['__DATE__', '__TIME__', '__TIMESTAMP__']]], timeout=timeout)
            if volatile.returncode or marker in volatile.stdout or marker in volatile.stderr:
                probe = subprocess.CompletedProcess(command, 1, '', '')
                reason = 'volatile builtin or unsupported preprocessing probe; compiling without cache'
        if probe.returncode == 0:
            env_deps = []
            if rust:
                depinfo = depfile.read_text().replace('\\\n', '')
                paths = shlex.split(depinfo.splitlines()[0].split(': ', 1)[1])
                env_deps = [line for line in depinfo.splitlines() if line.startswith('# env-dep:')]
                # Rust's dep-info omits the toolchain's prebuilt standard libraries.
                libdir = Path(subprocess.check_output([*dependencies, '--print', 'target-libdir'], text=True).strip())
                paths += [str(path) for pattern in ['*.rlib', '*.a'] for path in libdir.glob(pattern)]
            else:
                paths = shlex.split(probe.stdout.replace('\\\n', '').replace('swr_cache:', ''))
            paths += link_inputs
            # Relative inputs and debug compilation directories depend on cwd
            # even when argv and every discovered file byte are identical.
            inputs = {'command': command, 'cwd': str(Path.cwd()),
                      'dependencies': {path: digest(path) for path in sorted(set(paths))},
                      'compiler': digest(compiler), 'host': platform.platform(),
                      'compiler_version': subprocess.check_output([*driver, '--version'], text=True),
                      'environment': {name: os.environ.get(name) for name in
                                      ['SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CPATH',
                                       'CPLUS_INCLUDE_PATH', 'C_INCLUDE_PATH', 'LIBRARY_PATH']}}
            if rust:
                inputs['rust_environment_dependencies'] = hashlib.sha256('\n'.join(env_deps).encode()).hexdigest()
            key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
            reason = 'inputs changed or not compiled yet'
        elif reason == 'disabled':
            reason = 'dependency scan failed; compiling without cache'
    if key:
        entry = ROOT / 'target/cache/native' / key
        with exclusive(entry.with_suffix('.lock')):
            metadata = entry / 'manifest.json'
            binary = entry / 'binary'
            if metadata.exists() and binary.exists() and json.loads(metadata.read_text())['sha256'] == digest(binary):
                # Publish a fresh inode atomically; existing executable mappings
                # must never observe an in-place overwrite.
                copy_private(binary, output)
                result = subprocess.CompletedProcess(command, 0, '', '')
                hit, reason = True, 'compiler, flags, sources, headers and archives match'
            else:
                result = run_isolated(command, timeout=timeout)
                if result.returncode == 0:
                    entry.mkdir(parents=True, exist_ok=True)
                    copy_private(output, binary)
                    write_report(metadata, {'inputs': inputs, 'sha256': digest(binary)})
    else:
        result = run_isolated(command, timeout=timeout)
    return {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
            'cache_hit': hit, 'cache_key': key, 'cache_reason': reason,
            'seconds': round(time.monotonic() - started, 4)}
