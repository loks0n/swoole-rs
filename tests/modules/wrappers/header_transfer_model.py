#!/usr/bin/env python3
"""Concrete proposal-only Rust header ownership + actual public C++ map handoff; no production patch, parser, callbacks or fault/lifetime profiles."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
from tools.build_upstream import require_build_space
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--core',type=Path,required=True);p.add_argument('--include',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('Refusing existing receipt')
 folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True);rust=Path(__file__).with_suffix('.rs');cpp=Path(__file__).with_suffix('.cc');archive=folder/'libmodel.a';report={'scope':__doc__,'checks':[],'passed':False,'production_implementation':False,'public_header_changed':False,'Native_ASan_UBSan':True,'Rust_instrumented':False,'performance_qualified':False,'runtime_parser_or_user_callback_executed':False}
 def guard():
  try:require_build_space(ROOT)
  except RuntimeError as e:report.update(blocked=str(e),passed=False);write_report(a.output,report);raise
 command=['rustc','--edition=2024','--crate-type=staticlib','-Copt-level=2','-Cpanic=abort',str(rust),'-o',str(archive)];guard();r=run_isolated(command,timeout=90);report['rust_compile']={'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr};write_report(a.output,report)
 if r.returncode:return 1
 includes=[a.core,a.core/'include',a.core/'thirdparty',a.core/'thirdparty/llhttp',a.core.parent/'rust-prefix/include',*a.include]
 for standard in ['c++14','c++17']:
  binary=folder/standard;command=['c++','-std='+standard,'-O1','-g','-UNDEBUG','-DHAVE_CONFIG_H',*['-I'+str(x.resolve())for x in includes],'-fsanitize=address,undefined','-fno-sanitize-recover=all',str(cpp),str(archive),'-lpthread',*(['-ldl','-lm']if sys.platform=='linux'else[]),'-o',str(binary)];guard();r=run_isolated(command,timeout=90);row={'standard':standard,'command':command,'compile_exit':r.returncode,'compile_stdout':r.stdout,'compile_stderr':r.stderr,'passed':False};report['checks'].append(row);write_report(a.output,report)
  if r.returncode:return 1
  r=run_isolated([str(binary)],timeout=60);row.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr,passed=r.returncode==0 and not r.stderr);write_report(a.output,report)
  if not row['passed']:return 1
 report['passed']=True;write_report(a.output,report);print(json.dumps({'passed':True,'checks':[x['stdout']for x in report['checks']]}));return 0
if __name__=='__main__':sys.exit(main())
