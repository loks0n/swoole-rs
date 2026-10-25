#!/usr/bin/env python3
"""Actual Response write/end packetization bodies, native IO and lifetime facades."""
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
PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
CONTEXT = r'''
struct HttpContext;
bool swoole_http2_server_write(HttpContext*,zend_string*);
bool swoole_http2_server_end(HttpContext*,zend_string*);
struct HttpContext {
 bool http2=false,send_header_=false,send_chunked=false,send_trailer_=false;
 bool keepalive=true,upgrade=false,co=false,content_compressed=false,end_=false;
 bool websocket_compression=false,h2ok=true,empty_trailer=false;
 struct{int status=200;}response;
 struct{bool compression=false;}websocket_settings;
 struct{void*zobject=nullptr;zval*zheader=nullptr;}request;
 int fd=1;Server server;String buffer,compressed;String*zlib_buffer=&compressed;
 String*get_write_buffer(){oracle->event("buffer");return &buffer;}
 bool is_co_socket(){oracle->event("co-socket");return co;}
 Server*get_async_server(){oracle->event("server");return &server;}
 bool set_header(const char*,size_t,const char*,size_t,bool){oracle->event("websocket-header");return true;}
 void build_header(String*b,const char*,size_t){oracle->event("header");b->value="HTTP-header\r\n";b->update();send_header_=true;}
 bool send(HttpContext*,const char*p,size_t n){oracle->event("send:"+std::string(p?p:"",n));return ++oracle->sends!=oracle->failed_send;}
 void close(HttpContext*){oracle->event(end_?"close:ended":"close:pending");}
 int build_trailer(String*b){oracle->event("trailer");if(empty_trailer)return 0;b->value="x-trailer: value\r\n\r\n";b->update();return b->length;}
 void send_trailer(zval*);
 void write(zend_string*,zval*);
 void end(zend_string*,zval*);
};
bool swoole_http2_server_write(HttpContext*c,zend_string*){oracle->event("http2-write");return c->h2ok;}
bool swoole_http2_server_end(HttpContext*c,zend_string*){oracle->event("http2-end");return c->h2ok;}
'''
WRAPPER = r'''
Result run(unsigned bits,size_t length,bool null,bool ending,unsigned failed,unsigned hook,size_t fault){
 Oracle local;oracle=&local;local.failed_send=failed;local.fail=fault;HttpContext c;
 c.http2=bits&1;c.send_header_=bits&2;c.send_chunked=bits&4;c.send_trailer_=bits&8;
 c.keepalive=bits&16;c.upgrade=bits&32;c.co=bits&64;c.content_compressed=bits&128;
 c.response.status=(bits&256)?101:403;c.server.present=bits&512;
 c.server.connection.websocket_status=(bits&1024)?websocket::STATUS_HANDSHAKE:websocket::STATUS_ACTIVE;
 c.websocket_settings.compression=c.server.websocket_compression=bits&2048;c.h2ok=bits&4096;c.empty_trailer=bits&8192;
 zval header;header.value=(bits&256)?"permessage-deflate; client_max_window_bits":"unknown";
 c.request.zobject=&c;c.request.zheader=&header;
 c.buffer.value="old-buffer";c.buffer.update();c.compressed.value=(bits&4096)?"":"compressed";c.compressed.update();
 zend_string data;for(size_t i=0;i<length;i++)data.value.push_back(char(i));
 if(hook)local.hook=[&](const std::string&e){
  if(hook==1&&e=="header"){c.keepalive=!c.keepalive;c.content_compressed=!c.content_compressed;}
  if(hook==2&&e.find("send:")==0){c.keepalive=!c.keepalive;c.send_trailer_=!c.send_trailer_;}
  if(hook==3&&e=="trailer"){c.upgrade=!c.upgrade;c.co=!c.co;}
  if(hook==4&&e=="websocket-header"){c.response.status=403;c.server.connection.websocket_status=websocket::STATUS_HANDSHAKE;}
 };
 zval retval;retval.type=-1;Result r;
 try{if(ending)c.end(null?nullptr:&data,&retval);else c.write(&data,&retval);}catch(const Exit&){r.exited=true;}
 r.trace=local.trace;r.returned=retval.type;r.buffer=c.buffer.value;
 r.flags=(c.http2?1:0)|(c.send_header_?2:0)|(c.send_chunked?4:0)|(c.send_trailer_?8:0)|(c.keepalive?16:0)|(c.upgrade?32:0)|(c.co?64:0)|(c.content_compressed?128:0)|(c.end_?256:0)|(c.websocket_compression?512:0)|(c.server.connection.websocket_compression?1024:0);
 r.status=c.server.connection.websocket_status;return r;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--rust-sanitize', action='store_true')
    parser.add_argument('--without-compression', action='store_true')
    parser.add_argument('--without-zlib', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': __doc__, 'limitations': 'Actual write/end bodies, native buffer/codec/IO/HTTP2/WebSocket/Zend effects modeled. No real queue, socket suspension, fatal bailout, GC, native close repair or teardown proof. Conservative effect exits are not actual native allocator callback reproductions.',
              'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False,
              'compression_compiled': not args.without_compression, 'zlib_compiled': not args.without_zlib,
              'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-httpbindings-emission-') as temp:
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
        config = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':include/swoole_config.h']).decode()
        threshold = next(line for line in config.splitlines() if line.startswith('#define SW_HTTP_MAX_APPEND_DATA '))
        path = tree / dest
        path.parent.mkdir(parents=True)
        path.write_text(original)
        report['append_threshold'] = threshold
        patch = ROOT / 'migration/patches/httpbindings/0003-response-policy.patch'
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True)
        for name, text in [('upstream_emission', original), ('candidate_emission', path.read_text())]:
            bodies = '\n'.join(definition(text, 'void HttpContext::' + method + '(') for method in ['send_trailer', 'write', 'end'])
            p = tree / (name + '.cc')
            p.write_text('#include "emission_oracle.h"\n' + threshold + '\nnamespace ' + name + ' {\n' + CONTEXT + bodies + WRAPPER + '\n}\n')
        binary = tree / 'gate'
        cmd = ['c++', '-std=c++14', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I' + str(local), '-I' + str(ROOT / 'native/httpbindings'), str(tree / 'upstream_emission.cc'), str(tree / 'candidate_emission.cc'), str(local / 'emission_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if args.without_compression:
            cmd.append('-DEMISSION_NO_COMPRESSION')
        if args.without_zlib:
            cmd.append('-DEMISSION_NO_ZLIB')
        if sys.platform.startswith('linux'):
            cmd += ['-ldl', '-lpthread', '-lrt', '-lutil']
        result = run_isolated(cmd, timeout=90)
        report['compile'] = {'command': cmd, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if not result.returncode:
            result = run_isolated([str(binary)], timeout=120)
            report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
            if not result.returncode:
                report['outcome'] = json.loads(result.stdout.splitlines()[-1])
                report['passed'] = True
        write_report(args.output, report)
        print(json.dumps(report.get('outcome', report.get('run', report['compile']))))
        return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
