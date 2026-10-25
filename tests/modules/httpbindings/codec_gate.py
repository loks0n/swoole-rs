#!/usr/bin/env python3
"""Whole actual native codec-dispatch body with bounded native backend effects."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT,run_isolated,write_report
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
CONTEXT=r'''
struct HttpContext {
 int8_t compression_level=0,compression_method=0;bool accept_compression=false,content_compressed=false;uint32_t compression_min_length=0;
 std::shared_ptr<String>zlib_buffer;
 bool compress(const char*,size_t);
};
'''
WRAPPER=r'''
Result run(int level,int method,unsigned config,size_t fail){
 Oracle local;oracle=&local;local.config=config;HttpContext ctx;ctx.compression_level=level;ctx.compression_method=method;ctx.accept_compression=config&1;ctx.compression_min_length=(config&4)?128:0;
 ctx.zlib_buffer=std::make_shared<String>(17);ctx.zlib_buffer->length=5;ctx.zlib_buffer->offset=3;std::fill(ctx.zlib_buffer->storage.begin(),ctx.zlib_buffer->storage.end(),0x17);local.trace.clear();local.fail=fail;
 if(config&64)local.hook=[&](const std::string&event){if(event=="zstd-max"||event=="zstd-min")ctx.compression_level=97;};
 Result r;const std::string input(256,'x');
#ifdef SW_HAVE_COMPRESSION
 try{r.success=ctx.compress(input.data(),(config&2)?0:input.size());}catch(const Exit&){r.exited=true;}
#endif
 r.trace=local.trace;r.buffer=ctx.zlib_buffer->storage;r.size=ctx.zlib_buffer->size;r.length=ctx.zlib_buffer->length;r.offset=ctx.zlib_buffer->offset;r.level=ctx.compression_level;r.compressed=ctx.content_compressed;return r;
}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--capabilities',type=int,choices=range(8),default=7)
 group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--archive',type=Path);group.add_argument('--rust-sanitize',action='store_true');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();local=Path(__file__).resolve().parent
 report={'pin':PIN,'scope':__doc__,'limitations':'Native codec/library/allocation/warning facades, not actual Brotli/Zstd codecs or Zend allocator/GC/bailout. Zstd minimum-5 is an explicit facade bound to exercise capture/clamping; no installed-library bound claim. Capability0 compiles whole method out and supplies no codec proof. Rust std uninstrumented.','capabilities':args.capabilities,'native_sanitizers':True,'rust_instrumented':args.rust_sanitize,'passed':False}
 with tempfile.TemporaryDirectory(prefix='swr-httpbindings-codec-')as temp:
  tree=Path(temp)
  if args.rust_sanitize:
   args.archive=tree/'rust.a';cmd=['rustc','--edition=2024','-Zsanitizer=address','--crate-type=staticlib','-C','opt-level=3','-C','panic=abort',str(ROOT/'crates/httpbindings/src/lib.rs'),'-o',str(args.archive)];r=run_isolated(cmd,timeout=60,env={**os.environ,'RUSTC_BOOTSTRAP':'1'});report['rust_compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if r.returncode:write_report(args.output,report);return 1
  dest='ext-src/swoole_http_response.cc';original=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+dest]).decode();p=tree/dest;p.parent.mkdir(parents=True);p.write_text(original)
  patch=ROOT/'migration/patches/httpbindings/0003-response-policy.patch';subprocess.run(['git','apply','--check',str(patch)],cwd=tree,check=True);subprocess.run(['git','apply',str(patch)],cwd=tree,check=True)
  for name,text in [('upstream_codec',original),('candidate_codec',p.read_text())]:
   source=tree/(name+'.cc');source.write_text('#include "codec_oracle.h"\nnamespace '+name+' {\n'+CONTEXT+'\n#ifdef SW_HAVE_COMPRESSION\n'+definition(text,'bool HttpContext::compress(')+'\n#endif\n'+WRAPPER+'\n}\n')
  binary=tree/'gate';cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DCODEC_CAPABILITIES='+str(args.capabilities),'-I'+str(local),'-I'+str(ROOT/'native/httpbindings'),str(tree/'upstream_codec.cc'),str(tree/'candidate_codec.cc'),str(local/'codec_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
  if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
  r=run_isolated(cmd,timeout=90);report['compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
  if not r.returncode:
   r=run_isolated([str(binary)],timeout=90);report['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if not r.returncode:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['passed']=True
   elif r.returncode==77:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['unsupported']=True
  write_report(args.output,report);print(json.dumps(report.get('outcome',report.get('run',report['compile']))));return 0 if report['passed']else 2 if report.get('unsupported')else 1

if __name__=='__main__':sys.exit(main())
