#!/usr/bin/env python3
"""Compare actual pinned/patched HTTP helper bodies, without servers or parsers."""
import argparse
import hashlib
import io
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import COMMIT as PIN
ORIGINAL_TESTS = ['EncodeDecodeBasic', 'EncodeDecodeWithSpecialChars', 'get_method', 'get_method_str', 'parse_multipart_boundary']
FUNCTIONS = ['const char *get_status_message(', 'bool parse_multipart_boundary(', 'size_t url_decode(', 'char *url_encode(', 'int get_method(', 'const char *get_method_string(']
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def apply_http_patch(tree, patch, report):
    patch = Path(patch).resolve()
    manifest = ROOT/'migration/patches/http/manifest.json'
    entry = next((entry for entry in json.loads(manifest.read_text())['patches']
                  if (manifest.parent/entry['path']).resolve() == patch.resolve()), None)
    if entry is None:
        raise ValueError('HTTP patch is not in the committed module manifest')
    proof = apply_patch_verified(tree, patch, entry['upstream_paths'], entry['sha256'])
    proof['path'] = str(patch.relative_to(ROOT))
    report.setdefault('patch_application', []).append(proof)
    return proof

def body(source, signature):
    """The definition starting at signature. Braces count only in the first branch of
    each #if/#else, so alternatives such as `#if A switch (x) { #else switch (y) { #endif`
    are counted once."""
    start = source.index(signature); position = source.index('{', start); depth = 0; branches = []
    for line in source[position:].splitlines(keepends=True):
        directive = line.strip()
        if directive.startswith('#if'): branches.append(False)
        elif directive.startswith(('#else', '#elif')) and branches: branches[-1] = True
        elif directive.startswith('#endif') and branches: branches.pop()
        elif not any(branches):
            for offset, char in enumerate(line):
                depth += (char == '{') - (char == '}')
                if depth == 0 and char == '}':
                    return source[start:position + offset + 1]
        position += len(line)
    raise ValueError('Unterminated definition: ' + signature)
def extract(source, namespace):
    parts = ['static thread_local char http_status_message[128];']
    if 'static const char *method_strings[]' in source:
        array_start = source.index('static const char *method_strings[]'); array_end = source.index('};', array_start) + 2
        parts.insert(0, source[array_start:array_end])
    if 'static int url_htoi(' in source: parts.append(body(source, 'static int url_htoi('))
    parts += [body(source, signature) for signature in FUNCTIONS]
    return '#include "oracle.h"\nnamespace ' + namespace + ' {\n' + '\n'.join(parts) + '\n}\n'
def original_assertions(tests):
    adapter = r'''#define ASSERT_TRUE(value) do { if (!(value)) throw std::runtime_error("Original assertion: " #value); } while (false)
#define ASSERT_FALSE(value) ASSERT_TRUE(!(value))
#define ASSERT_EQ(a, b) ASSERT_TRUE((a) == (b))
#define EXPECT_EQ(a, b) ASSERT_EQ(a, b)
#define EXPECT_STREQ(a, b) ASSERT_TRUE(std::strcmp(a, b) == 0)
#define ASSERT_STREQ(a, b) EXPECT_STREQ(a, b)
#define TEST(group, name) static void original_##name()
'''
    output = '#include "oracle.h"\n' + adapter
    bodies = [body(tests, 'TEST(http_server, ' + name + ')') for name in ORIGINAL_TESTS]
    for engine in ['upstream', 'candidate']:
        output += 'namespace ' + engine + '_assertions {\nnamespace swoole { namespace http_server {\n'
        output += '\n'.join('using ::' + engine + '::' + signature.split('(')[0].split()[-1].lstrip('*') + ';' for signature in FUNCTIONS) + '\n}}\n'
        output += 'using namespace swoole::http_server;\n' + '\n'.join(bodies) + '\n}\n'
    output += 'void run_original_assertions() {\n'
    for engine in ['upstream', 'candidate']:
        output += '\n'.join(engine + '_assertions::original_' + name + '();' for name in ORIGINAL_TESTS) + '\n'
    return output + '}\n'
def add_archive_arguments(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--rust-sanitize', action='store_true', help='Privately instrument HTTP Rust with ASan; precompiled std remains uninstrumented')


def prepare_archive(args, tree, report):
    if not args.rust_sanitize:
        return True
    args.archive = tree/'libhttp-asan.a'
    codec = tree/'libswoole_rs_base64.rlib'
    codec_source = ROOT/'crates/base64/src/lib.rs'
    codec_command = ['rustc', '--edition=2024', '-Zsanitizer=address', '--crate-name=swoole_rs_base64', '--crate-type=rlib', '-C', 'opt-level=3', '-C', 'panic=abort', str(codec_source), '-o', str(codec)]
    compiled = run_isolated(codec_command, timeout=60, env={**os.environ, 'RUSTC_BOOTSTRAP': '1'})
    report['rust_codec_compile'] = {'command': codec_command, 'returncode': compiled.returncode, 'stdout': compiled.stdout, 'stderr': compiled.stderr}
    if compiled.returncode:
        return False
    command = ['rustc', '--edition=2024', '-Zsanitizer=address', '--extern', 'swoole_rs_base64='+str(codec), '--crate-type=staticlib', '-C', 'opt-level=3', '-C', 'panic=abort', str(ROOT/'crates/http/src/lib.rs'), '-o', str(args.archive)]
    compiled = run_isolated(command, timeout=60, env={**os.environ, 'RUSTC_BOOTSTRAP': '1'})
    report['rust_compile'] = {'command': command, 'returncode': compiled.returncode, 'stdout': compiled.stdout, 'stderr': compiled.stderr}
    if compiled.returncode:
        return False
    return True



def apply_static_header(tree, report):
    """Whole static TU now also consumes the additive, layout-preserving friend."""
    patch = ROOT / 'migration/patches/http/0003-static-inline.patch'
    apply_http_patch(tree, patch, report)


def prepare_index_buffer(tree, report):
    string_header = (tree/'include/swoole_string.h').read_text()
    template = body(string_header, 'size_t format_impl(')
    buffer_header = tree/'index_buffer.h'
    buffer_header.write_text('#pragma once\nclass IndexBuffer { public:\n std::vector<unsigned char> storage;char *str=nullptr;size_t size=0,length=6,offset=7;unsigned calls=0,fail=0;std::vector<size_t> events;\n enum FormatFlag{FORMAT_APPEND=1,FORMAT_GROW=2};\n explicit IndexBuffer(size_t capacity):storage(capacity,0xa5),size(capacity){str=reinterpret_cast<char*>(storage.data());if(capacity>=6)memcpy(str,"prefix",6);events.reserve(32);}\n void reserve(size_t requested){events.push_back(requested);if(++calls==fail)throw std::bad_alloc();size_t count=size==0?requested:SW_MEM_ALIGNED_SIZE(requested);storage.resize(count,0xa5);size=count;str=reinterpret_cast<char*>(storage.data());}\n void extend_align(size_t minimum){size_t count=SW_MEM_ALIGNED_SIZE(size*2);while(count<minimum)count*=2;reserve(count);}\n void append(const char *input,size_t count){if(length+count>size)reserve(length+count);memcpy(str+length,input,count);length+=count;}\n template <typename... Args>\n'+template+'\n};\n')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-helpers.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    patch = ROOT / 'migration/patches/http/0001-http-helpers.patch'
    report = {'pin': PIN, 'scope': 'Extracted actual first-party helper bodies; not full native TU, original parser/server tests or PHP parity', 'cpp_sanitized_rust_not_instrumented': True}
    with tempfile.TemporaryDirectory(prefix='swr-http-') as temp:
        tree = Path(temp)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'thirdparty/multipart_parser.h', 'src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree / member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree / 'src/protocol/http.cc'; original = source.read_text()
        tests = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':core-tests/src/server/http_server.cpp'], text=True)
        assertions = tree / 'original_assertions.cc'; assertions.write_text(original_assertions(tests))
        report['selected_original_tests'] = ORIGINAL_TESTS
        apply_http_patch(tree, patch, report)
        native_command = ['c++', '-std=c++14', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/http'), '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-c', str(source), '-o', str(tree/'http.o')]
        native_command += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        for namespace, text in [('upstream', original), ('candidate', source.read_text())]:
            extracted = tree / (namespace + '.cc'); extracted.write_text(extract(text, namespace))
        binary = tree / 'gate'
        command = ['c++', '-std=c++17', '-O1', '-g', '-I'+str(local), '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/http'), str(tree/'upstream.cc'), str(tree/'candidate.cc'), str(local/'gate.cc'), str(assertions), str(args.archive.resolve()), '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-lm', '-o', str(binary)]
        command += shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'openssl'], text=True))
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command
        compiled = run_isolated(command, timeout=60); report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        assert all(name in symbols for name in ['swr_v1_http_status', 'swr_v1_http_boundary', 'swr_v1_http_url_encode', 'swr_v1_http_url_decode', 'swr_v1_http_method'])
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1])
        report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
