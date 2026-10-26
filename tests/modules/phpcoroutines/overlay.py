"""The phpcoroutines overlays applied to pinned sources, for source-shape tests and gates.

Edit the overlays with tools/patches.py; this module only applies them.
"""
import json
from pathlib import Path
import subprocess
import tempfile

from activated_bodies import ACTIVATED_SIGNATURE

ROOT = Path(__file__).resolve().parents[3]
PATCHES = ROOT / 'migration/patches/phpcoroutines'
DEST = 'ext-src/swoole_coroutine_scheduler.cc'
SOURCE_SHA = '1138bb9799c96ac6ec75ad027eaa3fc5f40cce63f76939e71d9f753e1d80395c'
HEADER_DEST = 'ext-src/php_swoole_coroutine.h'
HEADER_SHA = '632c533e7dc6cd9429617ba5bd1cd3e465243116d48969951956266c74804ef3'
HEADER_SIGNATURES = [
    'static inline long get_cid() {', 'static inline long get_pcid(long cid = 0) {',
    'static inline long get_elapsed(long cid = 0) {', 'static inline PHPContext *get_context() {',
    'static inline PHPContext *get_origin_context(PHPContext *ctx) {',
    'static inline PHPContext *get_context_by_cid(long cid) {',
    'static inline ssize_t get_stack_usage(long cid) {', 'static inline bool is_schedulable(PHPContext *ctx) {',
    'static inline bool enable_scheduler() {', 'static inline bool disable_scheduler() {',
    'static inline long get_execute_time(long cid = 0) {', 'static void record_last_msec(PHPContext *ctx) {',
    ACTIVATED_SIGNATURE,
]


def body(source, signature):
    start = source.index(signature) + len(signature)
    depth = 1
    end = start
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end - 1]


def patched(destination, source):
    """The pinned `source` of `destination` with its phpcoroutines patch applied."""
    entries = [entry for entry in json.loads((PATCHES / 'manifest.json').read_text())['patches']
               if destination in entry['upstream_paths']]
    with tempfile.TemporaryDirectory() as tree:
        subprocess.run(['git', 'init', '-q', tree], check=True)
        path = Path(tree) / destination
        path.parent.mkdir(parents=True)
        path.write_text(source)
        for entry in entries:
            subprocess.run(['git', 'apply', '--include=' + destination, str(PATCHES / entry['path'])],
                           cwd=tree, check=True, capture_output=True)
        return path.read_text()


def selected(source):
    return patched(DEST, source)


def coroutine_selected(source):
    return patched('ext-src/swoole_coroutine.cc', source)


def system_selected(source):
    return patched('ext-src/swoole_coroutine_system.cc', source)


def header_selected(source):
    return patched(HEADER_DEST, source)
