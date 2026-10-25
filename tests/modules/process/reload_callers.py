#!/usr/bin/env python3
"""Actual native reload bodies; no real kill, process fork or copied class layout."""
import argparse,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tests/modules/ossupport'))
from archive_identity import sanitizer_outcome
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--patched-source',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);a=p.parse_args()
 for item in [a.source/'src/os/process_pool.cc',a.patched_source,a.library,a.archive]:
  if not item.is_file():p.error('Required existing source/artifact: '+str(item))
 out=ROOT/'target/process'/('reload-'+str(time.time_ns()));out.mkdir(parents=True);lib=a.library.resolve();before=sha(lib);rows=[]
 def checkpoint():
  report=dict(gate=False,platform=sys.platform,results=rows,library_path=str(lib),status='running');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 for mode,source in [('reference',a.source/'src/os/process_pool.cc'),('rust',a.patched_source)]:
  exe=out/mode;cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-DHAVE_CONFIG_H','-DSWRO_PROCESS_SOURCE="'+str(source)+'"','-I'+str(a.source),'-I'+str(a.source/'include'),'-I'+str(ROOT/'native/process'),str(ROOT/'tests/modules/process/reload_callers.cpp')]
  if mode=='rust':cmd+=['-DSWOOLE_RS_PROCESS',str(a.archive)]
  cmd+=[str(lib),'-Wl,-rpath,'+str(lib.parent),'-o',str(exe)]
  if sys.platform=='linux':cmd+=['-lpthread','-ldl','-lm']
  else:cmd+=['-I/opt/homebrew/opt/openssl@3/include']
  c=subprocess.run(cmd,text=True,capture_output=True);row=dict(mode=mode,command=cmd,compile_exit=c.returncode,compile_stdout=c.stdout,compile_stderr=c.stderr,library_before=before,status='failed');rows.append(row);checkpoint()
  if c.returncode==0:
   env=dict(os.environ)
   if sys.platform=='darwin':env['DYLD_PRINT_LIBRARIES']='1'
   probe=subprocess.run(['ldd',str(exe)]if sys.platform=='linux'else[str(exe)],text=True,capture_output=True,env=env,timeout=30);trace=probe.stdout+probe.stderr;pattern=r'^\s*libswoole[^ ]* => (/.*libswoole[^/ ]*) \(0x[0-9a-fA-F]+\)'if sys.platform=='linux'else r'^dyld\[\d+\]: (?:<[^>]+> )?(/.*libswoole[^/]*\.dylib)\s*$';loaded={str(Path(v).resolve())for v in re.findall(pattern,trace,re.M)};row.update(loader_trace=trace,loaded_paths=sorted(loaded),loaded_expected=probe.returncode==0 and loaded=={str(lib)});case_before=sha(lib);r=subprocess.run([str(exe)],text=True,capture_output=True,timeout=30);row.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr,case_library_before=case_before,library_after=sha(lib),sanitizer_outcome=sanitizer_outcome(r.stderr))
   if row['loaded_expected']and r.returncode==0 and row['library_after']==before and case_before==before:row['status']=row['sanitizer_outcome']
 report=dict(gate=all(r['status']=='passed'for r in rows),platform=sys.platform,results=rows,library_path=str(lib));(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'report.json');return int(not report['gate'])
if __name__=='__main__':raise SystemExit(main())
