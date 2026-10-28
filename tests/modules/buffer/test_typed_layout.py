"""Compile the hybrid build's Buffer header with SWOOLE_RS_BUFFER_TYPED omitted/0/1 and check its layout."""
import subprocess

import pytest

from tools.build_hybrid import hybrid_tree

PROBE = '''#include "swoole.h"
#include "swoole_buffer.h"
#include <type_traits>
static_assert(sizeof(swoole::Buffer)=={size},"Buffer carrier");
static_assert(sizeof(swoole::BufferChunk)==40 && alignof(swoole::BufferChunk)==8,"Public Chunk");
static_assert(offsetof(swoole::BufferChunk,length)==8 && offsetof(swoole::BufferChunk,offset)==12 && offsetof(swoole::BufferChunk,value)==16 && offsetof(swoole::BufferChunk,destroy)==32,"Frozen Chunk fields");
'''


def carrier(text):
    start = text.index('class Buffer {')
    depth = 0
    for i in range(text.index('{', start), len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError('Missing complete Buffer declaration')


@pytest.mark.parametrize('standard', ['c++14', 'c++17', 'c++20'])
def test_layout(archive, standard):
    _, flags = hybrid_tree(archive)
    flags = [flag for flag in flags if flag != '-DSWOOLE_RS_BUFFER_TYPED']
    declarations = {}
    for enabled in [None, 0, 1]:
        text = PROBE.format(size=8 if enabled == 1 else 56)
        command = ['c++', '-std=' + standard, *flags]
        if enabled is not None:
            command += ['-DSWOOLE_RS_BUFFER_TYPED=' + str(enabled)]
        result = subprocess.run(command + ['-fsyntax-only', '-x', 'c++', '-'], input=text, capture_output=True, text=True)
        assert result.returncode == 0, f'macro={enabled}: {result.stderr}'
        expanded = subprocess.run(command + ['-E', '-P', '-x', 'c++', '-'], input=text, capture_output=True, text=True)
        assert expanded.returncode == 0, expanded.stderr
        declarations[enabled] = carrier(expanded.stdout)
    assert declarations[None] == declarations[0], 'omitted macro must equal explicit zero'
