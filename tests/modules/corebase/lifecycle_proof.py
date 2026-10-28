"""Require actual lifecycle branches, including outlined native effect shims."""
from pathlib import Path
import platform
import re
import subprocess


def prove_lifecycle(library, selected, prefix, include_fork=False, include_init=False, include_task_tmp=False):
    library = Path(library)
    nm = subprocess.check_output(['nm', '-g', str(library)])
    disassembly = subprocess.check_output(['otool', '-tvV', str(library)] if platform.system() == 'Darwin'
                                         else ['objdump', '-d', '-C', str(library)])
    Path(str(prefix) + '.nm').write_bytes(nm)
    Path(str(prefix) + '.asm').write_bytes(disassembly)
    bodies = {}; current = None
    for line in disassembly.decode(errors='replace').splitlines():
        match = (re.match(r'^([_A-Za-z][_A-Za-z0-9.$]*):$', line) if platform.system() == 'Darwin'
                 else re.match(r'^[0-9a-fA-F]+ <(.+)>:$', line))
        if match:
            current = match[1]; bodies[current] = []
        elif current:
            bodies[current].append(line)
    exported = bool(re.search(rb'\b[Tt] _?swr_v1_corebase_lifecycle_next\s*$', nm, re.M))
    branch = re.compile(r'\b(?:bl|b|callq?|jmpq?)\s+(.+)')

    def branches(lines):
        return [m[1] for line in lines if (m := branch.search(line))]

    def rust_call(lines, symbol='swr_v1_corebase_lifecycle_next'):
        return any(re.search(r'\b_?' + symbol + r'\b', target) for target in branches(lines))

    helpers = {name: lines for name, lines in bodies.items()
               if 'corebase_lifecycle(' in name or 'corebase_lifecyclejj' in name}
    facades = [('swoole_clean()', '_Z12swoole_cleanv'),
               ('swoole_thread_init(bool)', '_Z18swoole_thread_initb'),
               ('swoole_thread_clean(bool)', '_Z19swoole_thread_cleanb')]
    if include_fork:
        facades += [('swoole_fork(int)', '_Z11swoole_forki'),
                    ('swoole_fork_exec(', '_Z16swoole_fork_exec')]
    if include_init:
        facades += [('swoole_init()', '_Z11swoole_initv')]
    if include_task_tmp:
        facades += [('swoole_set_task_tmpdir(', '_Z22swoole_set_task_tmpdir')]
    paths = {}
    for readable, mangled in facades:
        # GCC can split a function's unlikely blocks into a "[clone .cold]" body; the facade is the hot one.
        matches = [name for name in bodies if '@plt' not in name and '[clone ' not in name and (name == readable or name.lstrip('_') == mangled.lstrip('_')
                   or (readable.endswith('(') and (name.startswith(readable) or name.lstrip('_').startswith(mangled.lstrip('_')))))]
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous lifecycle facade: ' + readable)
        lines = bodies[matches[0]]
        symbol = ('swr_v1_corebase_init_next' if readable == 'swoole_init()' else
                  'swr_v1_corebase_task_tmp_next' if readable == 'swoole_set_task_tmpdir(' else
                  'swr_v1_corebase_lifecycle_next')
        if rust_call(lines, symbol):
            paths[readable] = 'direct Rust branch'
        else:
            called = [name for name, body in helpers.items()
                      if rust_call(body, symbol) and any(name in target for target in branches(lines))]
            paths[readable] = {'native_shims_calling_rust': called}
            if selected and not called:
                raise ValueError('Lifecycle facade has no actual path to Rust: ' + readable)
    if selected and not exported:
        raise ValueError('Selected library lacks lifecycle Rust definition')
    if include_init and selected and not re.search(rb'\b[Tt] _?swr_v1_corebase_init_next\s*$', nm, re.M):
        raise ValueError('Selected library lacks dedicated Rust initialization definition')
    if include_task_tmp and selected and not re.search(rb'\b[Tt] _?swr_v1_corebase_task_tmp_next\s*$', nm, re.M):
        raise ValueError('Selected library lacks dedicated Rust task-directory definition')
    if not selected and any(name in nm for name in [b'swr_v1_corebase_lifecycle_next', b'swr_v1_corebase_init_next', b'swr_v1_corebase_task_tmp_next']):
        raise ValueError('Native comparator contains lifecycle Rust symbol')
    return {'exported': exported, 'facade_paths': paths}
