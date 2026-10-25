#!/usr/bin/env python3
"""Actual selected DSO Rust disposition ABI via PHP FFI; positive metadata only, not native parser/Context/lifetime parity."""
from pathlib import Path
import argparse,json,hashlib,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--selected',type=Path,required=True);p.add_argument('--php',default='php');p.add_argument('--ffi-extension',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('Refusing an existing receipt')
 meta=json.load(open(a.selected/'export.json'));binary=a.selected/'swoole.so';assert sha(binary)==meta['files']['swoole.so']['sha256'];command=[a.php,'-n',*(['-d','extension='+str(a.ffi_extension)]if a.ffi_extension else[]),'-d','ffi.enable=true','-d','extension='+str(binary.resolve()),str(Path(__file__).with_suffix('.php')),str(binary.resolve())];r=run_isolated(command,timeout=30)
 report={'scope':__doc__,'source_ref':meta['source_ref'],'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'passed':False,'actual_native_wrapper_caller_executed':False,'whole_module_parity_passed':False,'Rust_instrumented':False,'Native_instrumented':False,'performance_qualified':False}
 if r.returncode==0 and not r.stderr:
  report['observed']=json.loads(r.stdout);report['passed']=report['observed']['passed']and report['observed']['checks']==1216
 write_report(a.output,report);print(json.dumps({'passed':report['passed'],'exit':r.returncode,'stderr':r.stderr[:500],'observed':report.get('observed')}));return int(not report['passed'])
if __name__=='__main__':sys.exit(main())
