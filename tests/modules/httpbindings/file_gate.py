#!/usr/bin/env python3
"""Actual Response send_file body and public signed range validation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_upstream import COMMIT as PIN
CONTEXT = r'''
struct HttpContext;
bool swoole_http2_server_send_file(HttpContext*,zend_string*,off_t,size_t);
struct HttpContext{
 bool http2=false,send_header_=false,end_=false,keepalive=false,accept_compression=true,file_ok=true,header_ok=true,h2ok=true;
 struct{void*zobject=nullptr;}response;String buffer;zval headers;
 String*get_write_buffer(){oracle->event("buffer");return &buffer;}
 void build_header(String*b,const char*,size_t length){oracle->event("header:"+std::to_string(length));b->value="header";b->update();send_header_=true;}
 bool send(HttpContext*,const char*p,size_t n){oracle->event("send:"+std::string(p?p:"",n));return header_ok;}
 bool sendfile(HttpContext*,zend_string*,off_t offset,size_t length){oracle->event("file:"+std::to_string(offset)+":"+std::to_string(length));return file_ok;}
 void close(HttpContext*){oracle->event(end_?"close:ended":"close:pending");}
 bool send_file(zend_string*,off_t,size_t);
};
bool swoole_http2_server_send_file(HttpContext*c,zend_string*,off_t,size_t){oracle->event("http2-file");return c->h2ok;}
'''
WRAPPER = r'''
FileResult run(unsigned bits,size_t length,unsigned hook,size_t fault){
 Oracle local;oracle=&local;local.fail=fault;HttpContext c;c.http2=bits&1;c.headers.type=(bits&2)?1:0;c.send_header_=bits&4;c.keepalive=bits&8;c.accept_compression=bits&16;c.file_ok=bits&32;c.header_ok=bits&64;c.h2ok=bits&256;c.end_=bits&128;c.response.zobject=&c.headers;
 c.buffer.value="old";c.buffer.update();c.headers.value=(bits&2)?"existing":"";
 if(hook)local.hook=[&](const std::string&e){if(hook==1&&e=="headers")c.headers.type=!c.headers.type;if(hook==2&&e.find("mime:")==0)c.send_header_=!c.send_header_;if(hook==3&&e.find("send:")==0)c.keepalive=!c.keepalive;if(hook==4&&e.find("file:")==0)c.keepalive=!c.keepalive;};
 zend_string file;file.value="private-file.bin";file.val=&file.value[0];file.len=file.value.size();FileResult r;
 try{r.returned=c.send_file(&file,17,length);}catch(const Exit&){r.exited=true;}
 r.flags=(c.send_header_?1:0)|(c.end_?2:0)|(c.keepalive?4:0)|(c.accept_compression?8:0);r.mime=c.headers.value;r.trace=local.trace;return r;
}
RangeResult range(int64_t size,int64_t offset,int64_t length){Oracle local;oracle=&local;zval result;result.type=-1;range_body(size,offset,length,&result);RangeResult r;r.trace=local.trace;r.length=length;r.returned=result.type;return r;}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--rust-sanitize', action='store_true')
    parser.add_argument('--without-compression', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': __doc__, 'limitations': 'Native MIME/header/buffer/IO/HTTP2/lifetime effects are facades. Undefined native signed subtraction overflow is excluded from equivalence; Rust safely rejects that arithmetic. No actual filesystem, GC/bailout, callback teardown, queue or performance proof.',
              'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False,
              'compression_compiled': not args.without_compression,
              'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-httpbindings-file-') as temp:
        tree = Path(temp)
        if args.rust_sanitize:
            args.archive = tree / 'rust.a'
            cmd = ['rustc', '--edition=2024', '-Zsanitizer=address', '--crate-type=staticlib', '-C', 'opt-level=3', '-C', 'panic=abort', str(ROOT / 'crates/httpbindings/src/lib.rs'), '-o', str(args.archive)]
            result = run_isolated(cmd, timeout=60, env={**os.environ, 'RUSTC_BOOTSTRAP': '1'})
            report['rust_compile'] = {'command': cmd, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
            if result.returncode:
                write_report(args.output, report)
                return 1
        dest = 'ext-src/swoole_http_response.cc'
        original = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':' + dest]).decode()
        path = tree / dest
        path.parent.mkdir(parents=True)
        path.write_text(original)
        patch = ROOT / 'migration/patches/httpbindings/0003-response-policy.patch'
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True)
        for name, text in [('upstream_file', original), ('candidate_file', path.read_text())]:
            body = definition(text, 'bool HttpContext::send_file(')
            public = definition(text, 'static PHP_METHOD(swoole_http_response, sendfile) {')
            a = public.index('    if (file_stat.st_size < offset) {') if name == 'upstream_file' else public.index('    static_assert(sizeof(off_t)')
            b = public.index('    if (ctx->onAfterResponse) {', a)
            range_body = 'void range_body(int64_t size,int64_t offset,int64_t&length,zval*return_value){struct{off_t st_size;}file_stat{size};\n' + public[a:b] + '\nreturn_value->type=1;\n}\n'
            p = tree / (name + '.cc')
            p.write_text('#include "file_oracle.h"\nnamespace ' + name + ' {\n' + CONTEXT + body + range_body + WRAPPER + '\n}\n')
        binary = tree / 'gate'
        cmd = ['c++', '-std=c++14', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I' + str(local), '-I' + str(ROOT / 'native/httpbindings'), str(tree / 'upstream_file.cc'), str(tree / 'candidate_file.cc'), str(local / 'file_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if args.without_compression:
            cmd.append('-DEMISSION_NO_COMPRESSION')
        if sys.platform.startswith('linux'):
            cmd += ['-ldl', '-lpthread', '-lrt', '-lutil']
        result = run_isolated(cmd, timeout=90)
        report['compile'] = {'command': cmd, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if not result.returncode:
            result = run_isolated([str(binary)], timeout=90)
            report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
            if not result.returncode:
                report['outcome'] = json.loads(result.stdout.splitlines()[-1])
                report['passed'] = True
        write_report(args.output, report)
        print(json.dumps(report.get('outcome', report.get('run', report['compile']))))
        return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
