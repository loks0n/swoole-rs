#!/usr/bin/env python3
"""Differential request framing checks with deterministic native facades."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def original_frames(tests):
    adapter = r'''#define ASSERT_TRUE(value) do { if (!(value)) throw std::runtime_error("Original assertion: " #value); } while (false)
#define ASSERT_FALSE(value) ASSERT_TRUE(!(value))
#define ASSERT_EQ(a, b) ASSERT_TRUE((a) == (b))
#define EXPECT_EQ(a, b) ASSERT_EQ(a, b)
#define TEST(group, name) static void original_##name()
'''
    result = '#include "framing_oracle.h"\n' + adapter
    bodies = [body(tests, 'TEST(http_server, ' + name + ')') for name in ['get_protocol', 'has_expect_header', 'all_method']]
    for engine in ['upstream_frame', 'candidate_frame']:
        result += 'namespace ' + engine + '_assertions {\n'
        result += 'namespace swoole { namespace http_server { using Request = ::' + engine + '::Request; using ::'+engine+'::get_method_string; }}\nnamespace http_server=swoole::http_server;\n'
        result += 'struct String : ::' + engine + '::Buffer { explicit String(const std::string &input="") { storage=input; sync(); } };\n'
        result += 'static ::' + engine + '::Request req{};\n'
        result += 'static void SetRequestContent(const std::string &value) { delete static_cast<String *>(req.buffer_); req={}; req.buffer_=new String(value); }\n'
        result += 'static void SetRequestContent(String *value) { delete static_cast<String *>(req.buffer_); req={}; req.buffer_=value; }\n'
        result += 'static ::' + engine + '::Buffer *sw_tg_buffer() { static ::' + engine + '::Buffer buffer{}; return &buffer; }\n'
        result += 'static int swoole_rand(int minimum, int) { return minimum; }\n' + '\n'.join(bodies)
        result += '\nvoid run() { original_get_protocol(); original_has_expect_header(); original_all_method(); delete static_cast<String *>(req.buffer_); req.buffer_=nullptr; }\n}\n'
    return result + 'void run_original_frames() { upstream_frame_assertions::run(); candidate_frame_assertions::run(); }\n'
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-framing.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    patch = ROOT/'migration/patches/http/0001-http-helpers.patch'
    report = {'pin': PIN, 'scope': 'Actual pinned/patched framing method bodies with POD request/buffer facades; not full server/parser/PHP parity', 'native_sanitizers': True, 'rust_instrumented': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-framing-') as temp:
        tree = Path(temp)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'thirdparty/multipart_parser.h', 'src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/protocol/http.cc'; original = source.read_text()
        tests = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':core-tests/src/server/http_server.cpp'], text=True)
        assertions = tree/'original_frames.cc'; assertions.write_text(original_frames(tests))
        report['selected_original_tests'] = ['get_protocol', 'has_expect_header', 'all_method']
        report['entropy_fixture'] = 'minimum requested count of deterministic base64 alphabet bytes; original assertions unchanged'
        apply_http_patch(tree, patch, report)
        flags = ['-std=c++17', '-DSWOOLE_RS_HTTP', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        signatures = ['int Request::get_protocol(', 'int Request::get_header_length(', 'int Request::get_chunked_body_length(', 'bool Request::has_expect_header(', 'std::string Request::get_header(', 'const char *get_method_string(']
        for namespace, text in [('upstream_frame', original), ('candidate_frame', source.read_text())]:
            parts = []
            if 'static const char *method_strings[]' in text:
                start = text.index('static const char *method_strings[]'); end = text.index('};',start)+2; parts.append(text[start:end])
            if 'int frame_request(' in text: parts.append(body(text, 'int frame_request('))
            parts += [body(text, signature) for signature in signatures]
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "framing_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_frame.cc'), str(tree/'candidate_frame.cc'), str(local/'framing_gate.cc'), str(assertions), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        assert 'swr_v1_http_chunk_step' in subprocess.check_output(['nm', '-g', str(binary)], text=True)
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
