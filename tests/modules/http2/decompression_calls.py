#!/usr/bin/env python3
"""Complete pinned/patched HTTP2 decompression functions using real host zlib."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate
from settings_calls import body, select_overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--core-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include', action='append', default=[])
    args = parser.parse_args()
    core = json.loads(args.core_report.read_text())
    if not core['passed']:
        raise ValueError('Completed passing core receipt required')
    artifacts = args.core_report.parent / (args.core_report.stem + '-artifacts')
    archive = Path(core.get('archive', artifacts / 'libhttp2.a'))
    header = gate.ROOT / 'native/http2/rust_http2.h'
    name = 'ext-src/swoole_http2_client_coro.cc'
    selected = artifacts / 'overlay' / name
    if gate.digest(archive) != core['archive_sha256'] or gate.digest(selected) != core['patched_sources'][name]:
        raise ValueError('Frozen archive/overlay identity changed')
    if gate.digest(header) != core['module_header_sha256']:
        raise ValueError('Module header changed')
    original = subprocess.check_output(['git', 'show', f'{gate.PIN}:{name}'], cwd=args.source, text=True)
    report = {'passed': False, 'scope': __doc__, 'upstream_commit': gate.PIN,
              'commands': [], 'gaps': [
                  'Real PHP String custody, PHP allocator/Zend bailout, GC and coroutine runtime',
                  'String clear/growth allocation are native doubles; zlib itself executes for real',
                  'Native tracing disabled; no invalidated raw pointer or invalid input bounds',
                  'Rust sanitizer instrumentation and optimized performance']}
    pieces = []
    for variant, text in [('native', original), ('rust', select_overlay(selected.read_text()))]:
        fragment = body(text, 'int php_swoole_zlib_decompress(')
        pieces.append('namespace ' + variant + ' {int decompress(z_stream*stream,String*buffer,char*body,int length){' + fragment + '}}')
    prelude = r'''
#include "swoole_http2.h"
#define SW_USE_RUST_HTTP2
#include "rust_http2.h"
#include <zlib.h>
#include <string>
#include <vector>
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <limits>
#undef swoole_trace_log
#define swoole_trace_log(...) ((void)0)
static std::vector<std::string>effects;
static unsigned throw_at,mutation;
static z_stream *current;
static void event(const std::string&what){effects.push_back(what);if(throw_at==effects.size())throw std::runtime_error("native allocation");}
struct String {size_t length=0,size;char*str;std::vector<char>bytes;
 explicit String(size_t capacity):size(capacity),bytes(capacity){str=bytes.data();}
 void clear(){event("clear:"+std::to_string(length));length=0;}
 void extend(){event("extend:"+std::to_string(size)+":"+std::to_string(length));size*=2;bytes.resize(size);str=bytes.data();if(mutation&1)current->avail_in=0;if(mutation&2)current->total_out=0;}
};
static int traced_inflate(z_stream*stream,int flush){int status=::inflate(stream,flush);effects.push_back("inflate:"+std::to_string(status)+":"+std::to_string(stream->avail_in)+":"+std::to_string(stream->avail_out)+":"+std::to_string(stream->total_in)+":"+std::to_string(stream->total_out));return status;}
#define inflate traced_inflate
'''
    driver = r'''
#undef inflate
struct Result{std::vector<std::string>events;std::vector<int>returns;std::string bytes,exception;size_t length=0,capacity=0;unsigned available=0;unsigned long total_in=0,total_out=0;};
static std::string compress(const std::string&data,int level){z_stream stream{};if(deflateInit2(&stream,level,Z_DEFLATED,MAX_WBITS+16,8,Z_DEFAULT_STRATEGY)!=Z_OK)std::abort();std::string compressed(compressBound(data.size())+64,'\0');stream.next_in=(Bytef*)data.data();stream.avail_in=data.size();stream.next_out=(Bytef*)compressed.data();stream.avail_out=compressed.size();if(deflate(&stream,Z_FINISH)!=Z_STREAM_END)std::abort();compressed.resize(stream.total_out);deflateEnd(&stream);return compressed;}
static std::string payload(unsigned length,unsigned pattern){std::string data(length,'a');uint32_t random=0x12345678;for(unsigned i=0;i<length;++i){random^=random<<13;random^=random>>17;random^=random<<5;if(pattern==1)data[i]=char(i);if(pattern==2)data[i]=char(random);}return data;}
template<bool rust>Result execute(std::string input,size_t capacity,unsigned split,unsigned thrown,unsigned change){
 z_stream stream{};if(inflateInit2(&stream,MAX_WBITS+16)!=Z_OK)std::abort();String buffer(capacity);current=&stream;effects.clear();throw_at=thrown;mutation=change;Result r;
 try{auto call=[&](char*p,size_t n){int rc=rust?::rust::decompress(&stream,&buffer,p,n) : ::native::decompress(&stream,&buffer,p,n);r.returns.push_back(rc);r.bytes.append(buffer.str,buffer.length);return rc;};size_t cut=split==0?input.size():split==1?0:split==2?1:input.size()/2;if(call(input.data(),cut)==SW_OK&&cut<input.size())call(input.data()+cut,input.size()-cut);}
 catch(const std::runtime_error&e){r.exception=e.what();}
 r.events=effects;r.length=buffer.length;r.capacity=buffer.size;r.available=stream.avail_in;r.total_in=stream.total_in;r.total_out=stream.total_out;inflateEnd(&stream);current=nullptr;return r;
}
static bool same(const Result&a,const Result&b){return a.events==b.events&&a.returns==b.returns&&a.bytes==b.bytes&&a.exception==b.exception&&a.length==b.length&&a.capacity==b.capacity&&a.available==b.available&&a.total_in==b.total_in&&a.total_out==b.total_out;}
int main(){size_t count=0;
if(Z_OK!=0||Z_STREAM_END!=1)return 5;
for(unsigned length:{0u,1u,17u,4096u,16384u,65536u})for(unsigned pattern:{0u,1u,2u})for(int level:{0,1,9}){
 auto original=payload(length,pattern);auto encoded=compress(original,level);
 for(size_t capacity:{size_t(1),size_t(7),size_t(4095),size_t(4096),size_t(8193)})for(unsigned split=0;split<4;++split)for(unsigned change=0;change<4;++change){auto a=execute<false>(encoded,capacity,split,0,change);auto b=execute<true>(encoded,capacity,split,0,change);if(!same(a,b)){std::cerr<<"real zlib mismatch length="<<length<<" pattern="<<pattern<<" level="<<level<<" capacity="<<capacity<<" split="<<split<<" mutation="<<change<<"\n";return 1;}if(split==0&&change==0&&(a.returns!=std::vector<int>{SW_OK}||a.bytes!=original)){std::cerr<<"full gzip output mismatch\n";return 2;}++count;}
 for(unsigned kind=0;kind<4;++kind){auto input=encoded;if(kind==1)input.resize(input.size()-1);if(kind==2)input[0]^=127;if(kind==3)input=original;
 for(size_t capacity:{size_t(1),size_t(4096)})for(unsigned thrown:{0u,1u,2u,3u,5u,9u})for(unsigned change=0;change<4;++change){auto a=execute<false>(input,capacity,0,thrown,change);auto b=execute<true>(input,capacity,0,thrown,change);if(!same(a,b)){std::cerr<<"zlib error/exception prefix mismatch\n";return 3;}++count;}}
}
// Pure width/status boundaries do not allocate or form invalid buffer pointers.
for(unsigned after:{0u,1u})for(int status:{-6,-5,-4,-3,-2,-1,0,1,2,3,99})for(size_t length:{size_t(0),size_t(1),size_t(4095),SIZE_MAX-size_t(4096),SIZE_MAX})for(size_t capacity:{size_t(0),size_t(1),size_t(4096),SIZE_MAX})for(unsigned available:{0u,1u,UINT32_MAX}){
 SwRsHttp2DecompressPlan plan;sw_rs_http2_decompress_plan(after,status,length,capacity,available,&plan);unsigned expected=after?(available==0?1:2):status==1?1:status==0?(length+4096>=capacity?3:available==0?1:2):0;if(plan.publish_length!=unsigned(!after&&status>=0)||plan.action!=expected)return 4;++count;}
std::cout<<"{\"passed\":true,\"decompression_cases\":"<<count<<",\"zlib_compile\":\""<<ZLIB_VERSION<<"\",\"zlib_runtime\":\""<<zlibVersion()<<"\"}\n";
}
'''
    work = args.output.parent / (args.output.stem + '-artifacts')
    work.mkdir(parents=True, exist_ok=False)
    cpp = work / 'decompression.cpp'
    cpp.write_text(prelude + '\n'.join(pieces) + driver)
    executable = work / 'decompression'
    command = ['c++', '-std=c++17', '-O1', '-fsanitize=address,undefined', '-fno-sanitize=alignment',
               '-fno-omit-frame-pointer', '-I', str(gate.ROOT / 'native/http2'), '-I', str(args.source / 'include')]
    for include in args.include:
        command += ['-I', include]
    command += [str(cpp), str(archive), '-lz', '-o', str(executable)]
    for cmd in [command, [str(executable)]]:
        result = subprocess.run(cmd, capture_output=True, text=True)
        report['commands'].append({'command': cmd, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            break
        if cmd != command:
            report.update(json.loads(result.stdout))
    if gate.digest(header) != core['module_header_sha256']:
        report['passed'] = False
        report['error'] = 'Module header changed during checks'
    report['native_sanitizers'] = ['address', 'undefined except alignment']
    report['rust_sanitized'] = False
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'report': str(args.output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
