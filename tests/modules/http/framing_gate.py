#!/usr/bin/env python3
"""Differential request framing checks with deterministic native facades."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
from gate import PIN, body, Sides, run
from tools.harness import write_report

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
    report = {'pin': PIN, 'scope': 'Actual pinned/patched framing method bodies with POD request/buffer facades; not full server/parser/PHP parity', 'native_sanitizers': True, 'rust_instrumented': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-framing-') as temp:
        tree = Path(temp); path = 'src/protocol/http.cc'
        sides = Sides(args.source, args.archive, tree, 'thirdparty/multipart_parser.h', path)
        tests = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':core-tests/src/server/http_server.cpp'], text=True)
        assertions = tree/'original_frames.cc'; assertions.write_text(original_frames(tests))
        report['selected_original_tests'] = ['get_protocol', 'has_expect_header', 'all_method']
        report['entropy_fixture'] = 'minimum requested count of deterministic base64 alphabet bytes; original assertions unchanged'
        if not sides.native(report, path): write_report(args.output, report); return 1
        signatures = ['int Request::get_protocol(', 'int Request::get_header_length(', 'int Request::get_chunked_body_length(', 'bool Request::has_expect_header(', 'std::string Request::get_header(', 'const char *get_method_string(']
        for namespace, text in [('upstream_frame', sides.original(path)), ('candidate_frame', sides.selected(path))]:
            parts = []
            if 'static const char *method_strings[]' in text:
                start = text.index('static const char *method_strings[]'); end = text.index('};',start)+2; parts.append(text[start:end])
            if 'int frame_request(' in text: parts.append(body(text, 'int frame_request('))
            parts += [body(text, signature) for signature in signatures]
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "framing_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        units = [('upstream', tree/'upstream_frame.cc'), ('candidate', tree/'candidate_frame.cc'), ('candidate', local/'framing_gate.cc'), ('candidate', assertions)]
        if not sides.build(binary, units, args.archive.resolve(), report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_chunk_step'], args.output, report)
if __name__ == '__main__': sys.exit(main())
