#!/usr/bin/env python3
"""Actual coroutine HTTP startup option body and ordered native Zend effects."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT,run_isolated,write_report
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
WRAPPER=r'''
Result run(const Input&in,size_t fail){
 Oracle local;oracle=&local;local.dir_ok=in.dir_ok;HashTable table=in.table;local.table=&table;HttpServer ctx;
 auto original=std::make_shared<std::unordered_set<std::string>>();original->insert("old");ctx.compression_types=original;
 ctx.upload_tmp_dir=strdup("old");local.allocated.insert(ctx.upload_tmp_dir);local.trace.clear();local.fail=fail;
 if(in.hook)local.hook=[&](const std::string&event){
  if(in.hook==1&&event.find("truth:")==0){auto&z=table["compression_level"];z.kind=1;z.number=199;z.text="reentered";}
  if(in.hook==2&&event=="websocket"){auto&z=table["upload_tmp_dir"];z.kind=3;z.text="reentered-directory";}
  if(in.hook==3&&event=="new-types"){auto i=table.find("http_compression_types");if(i!=table.end())i->second.kind=4;}
 };
 Result r;try{apply(&ctx,&table);}catch(const Exit&){r.exited=true;}
 r.trace=local.trace;r.flags=ctx.parse_cookie|(ctx.parse_post?2:0)|(ctx.parse_files?4:0)|(ctx.compression?8:0);r.level=ctx.compression_level;r.minimum=ctx.compression_min_length;r.websocket=ctx.websocket_settings;r.replaced=ctx.compression_types!=original;
 if(ctx.compression_types)r.types=std::set<std::string>(ctx.compression_types->begin(),ctx.compression_types->end());
 r.upload=ctx.upload_tmp_dir?(local.allocated.count(ctx.upload_tmp_dir)?ctx.upload_tmp_dir:"(freed)"):"(null)";
 r.completed=local.completed;r.returned_false=local.returned_false;return r;
}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True)
 group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--archive',type=Path);group.add_argument('--rust-sanitize',action='store_true');parser.add_argument('--without-compression',action='store_true');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();local=Path(__file__).resolve().parent
 report={'pin':PIN,'scope':__doc__,'limitations':'Only actual startup settings body after native socket/properties/callable setup and before accept. Native Zend/allocator/directory/WebSocket/fatal effects are facades; not actual GC/bailout/teardown. Conservative exits at native effect boundaries can expose freed-field prefixes; not a real strdup-failure reproduction or cleanup claim.','compression_compiled':not args.without_compression,'rust_instrumented':args.rust_sanitize,'rust_std_instrumented':False,'passed':False}
 with tempfile.TemporaryDirectory(prefix='swr-httpbindings-settings-')as temp:
  tree=Path(temp)
  if args.rust_sanitize:
   args.archive=tree/'rust.a';cmd=['rustc','--edition=2024','-Zsanitizer=address','--crate-type=staticlib','-C','opt-level=3','-C','panic=abort',str(ROOT/'crates/httpbindings/src/lib.rs'),'-o',str(args.archive)];r=run_isolated(cmd,timeout=60,env={**os.environ,'RUSTC_BOOTSTRAP':'1'});report['rust_compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if r.returncode:write_report(args.output,report);return 1
  dest='ext-src/swoole_http_server_coro.cc';original=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+dest]).decode();p=tree/dest;p.parent.mkdir(parents=True);p.write_text(original)
  patch=ROOT/'migration/patches/httpbindings/0005-coro-server-policy.patch';subprocess.run(['git','apply','--check',str(patch)],cwd=tree,check=True);subprocess.run(['git','apply',str(patch)],cwd=tree,check=True)
  for name,text in [('upstream_settings',original),('candidate_settings',p.read_text())]:
   start=text.index('static PHP_METHOD(swoole_http_server_coro, start) {');a=text.index('    // parse cookie header',start)if name=='upstream_settings'else text.index('    swr_v1_httpbindings_settings_cursor settings{};',start);b=text.index('    hs->running = true;',a)
   body='void apply(HttpServer*hs,HashTable*vht){zval*ztmp=nullptr;\n'+text[a:b]+'\n oracle->completed=true;\n}\n'
   out=tree/(name+'.cc');out.write_text('#include "settings_oracle.h"\nnamespace '+name+' {\n'+body+WRAPPER+'\n}\n')
  binary=tree/'gate';cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(local),'-I'+str(ROOT/'native/httpbindings'),str(tree/'upstream_settings.cc'),str(tree/'candidate_settings.cc'),str(local/'settings_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
  if args.without_compression:cmd.append('-DSETTINGS_NO_COMPRESSION')
  if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
  r=run_isolated(cmd,timeout=90);report['compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
  if not r.returncode:
   r=run_isolated([str(binary)],timeout=90);report['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if not r.returncode:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['passed']=True
  write_report(args.output,report);print(json.dumps(report.get('outcome',report.get('run',report['compile']))));return 0 if report['passed']else 1

if __name__=='__main__':sys.exit(main())
