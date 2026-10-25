#!/usr/bin/env python3
"""Actual MIME callers with positive C++ allocation observations and Rust extent cases; no faults, limits, callbacks or clock."""
from pathlib import Path
import argparse,json,sys
import overlay
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
from tools.build_upstream import require_build_space
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--include',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,required=True);a=p.parse_args();overlay.SOURCE=a.source
 if a.output.exists():p.error('Refusing an existing receipt')
 folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True);generated=overlay.generated();report={'scope':__doc__,'pin':overlay.PIN,'results':[],'sdk':[],'passed':False,'Rust_instrumented':False,'Native_ASan_UBSan':True,'fault_or_limit_or_timing_executed':False,'whole_module_parity_passed':False,'performance_qualified':False}
 includes=[a.core,a.core/'include',a.core/'thirdparty',a.core/'thirdparty/llhttp',a.core.parent/'rust-prefix/include',*a.include]
 base=['c++','-std=c++14','-O1','-g','-UNDEBUG','-DHAVE_CONFIG_H','-DSWOOLE_RS_FRAMING','-I'+str(ROOT/'native/framing'),*['-I'+str(x.resolve())for x in includes]]
 def guard():
  try:require_build_space(ROOT)
  except RuntimeError as e:report.update(blocked=str(e),passed=False);write_report(a.output,report);raise
 for engine in ['original','selected']:
  source=folder/(engine+'.cc');source.write_text(overlay.original('src/protocol/mime_type.cc')if engine=='original'else generated['src/protocol/mime_type.cc']);binary=folder/engine;command=[*base,*(['-DCANDIDATE']if engine=='selected'else[]),'-fsanitize=address,undefined','-fno-sanitize-recover=all',str(Path(__file__).with_suffix('.cc')),str(source),*([str(a.archive.resolve()),'-lpthread']if engine=='selected'else[]),*(['-ldl','-lm']if sys.platform=='linux'else[]),'-o',str(binary)];guard();r=run_isolated(command,timeout=90);row={'engine':engine,'command':command,'compile_exit':r.returncode,'compile_stdout':r.stdout,'compile_stderr':r.stderr,'passed':False};report['results'].append(row);write_report(a.output,report)
  if r.returncode:return 1
  r=run_isolated([str(binary)],timeout=30);row.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr,passed=r.returncode==0 and not r.stderr);write_report(a.output,report)
  if not row['passed']:return 1
 for engine in ['original','selected']:
  for name in ['src/protocol/base.cc','src/protocol/mime_type.cc']:
   source=folder/(engine+'-'+Path(name).name);source.write_text(overlay.original(name)if engine=='original'else generated[name]);command=[*base,'-fsyntax-only',str(source)];guard();r=run_isolated(command,timeout=90);report['sdk'].append({'engine':engine,'source':name,'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr});write_report(a.output,report)
   if r.returncode:return 1
 report['passed']=True;write_report(a.output,report);print(json.dumps({'passed':True,'sdk':len(report['sdk']),'models':[x['stdout']for x in report['results']]}));return 0
if __name__=='__main__':sys.exit(main())
