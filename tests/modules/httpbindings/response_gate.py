#!/usr/bin/env python3
"""Actual Response known-header classifier against the pinned native one."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition, rust_declarations
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.build_hybrid import hybrid_tree
from tools.harness import ROOT,run_isolated,write_report
from tools.build_upstream import COMMIT as PIN
WRAPPERS=r'''
int header(const std::string&name){return http_response_parse_header_name(name.data(),name.size());}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True)
 parser.add_argument('--archive',type=Path,required=True,help='Rust archive of the hybrid build under test')
 parser.add_argument('--native-libc',action='store_true');parser.add_argument('--locale',default='C');parser.add_argument('--without-compression',action='store_true');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();local=Path(__file__).resolve().parent
 report={'pin':PIN,'scope':__doc__,'limitations':'Header-name classification only; build_header itself is upstream\'s (#366). Not Zend/codec/GC/lifetime proof; not called original PHPT passes.','native_sanitizers':not args.native_libc,'rust_instrumented':False,'locale':args.locale,'compression_compiled':not args.without_compression,'passed':False}
 with tempfile.TemporaryDirectory(prefix='swr-httpbindings-response-')as temp:
  tree=Path(temp)
  # Upstream side from the pin, candidate side from the hybrid build's fully patched tree.
  hybrid_source,hybrid_flags=hybrid_tree(args.archive);names=['ext-src/swoole_http_response.cc','ext-src/php_swoole_http.h','include/swoole.h','src/core/base.cc']
  original={n:subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+n]).decode()for n in names}
  selected={n:(hybrid_source/n).read_text()for n in names}
  for name,texts in [('upstream_response',original),('candidate_response',selected)]:
   enums=texts['ext-src/php_swoole_http.h'];a=enums.index('enum swHttpHeaderFlag {');b=enums.index('};',a)+2
   helpers=enums[a:b]+'\nstatic constexpr int HTTP_HEAD=2,HTTP_POST=3;\n'+definition(texts['include/swoole.h'],'static inline unsigned int swoole_strcaseeq(')+'\n'+definition(texts['src/core/base.cc'],'int swoole_itoa(')
   source=texts['ext-src/swoole_http_response.cc']
   parts=[definition(source,'static int http_response_parse_header_name(')]
   p=tree/(name+'.cc');p.write_text('#include "response_oracle.h"\n'+rust_declarations(helpers,hybrid_flags)+'namespace '+name+' {\n'+helpers+'\n'+'\n'.join(parts)+'\n'+WRAPPERS+'\n}\n')
  binary=tree/'gate';cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(local),'-I'+str(ROOT/'native/httpbindings'),*hybrid_flags,str(tree/'upstream_response.cc'),str(tree/'candidate_response.cc'),str(local/'response_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
  if args.native_libc:cmd=[arg for arg in cmd if not arg.startswith('-fsanitize=')and arg!='-fno-sanitize-recover=all']
  if args.without_compression:cmd.append('-DRESPONSE_NO_COMPRESSION')
  if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
  r=run_isolated(cmd,timeout=90);report['compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
  if not r.returncode:
   r=run_isolated([str(binary)],timeout=90,env={**os.environ,'HTTPBINDINGS_LOCALE':args.locale});report['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if not r.returncode:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['passed']=True
  write_report(args.output,report);print(json.dumps(report.get('outcome',report.get('run',report['compile']))));return 0 if report['passed']else 1

if __name__=='__main__':sys.exit(main())
