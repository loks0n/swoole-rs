#!/usr/bin/env python3
"""Actual timing seed/member/getter/switch fragments with inert clocks and Context.

No Coroutine execution, switching, registry, callback, allocation/lifetime or PHP
qualification. Full header/backend SDK compilation is a separate required check.
"""
import argparse,hashlib,json,subprocess,sys,uuid,tarfile,io
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report

def find(text,anchor,start=0):
 if anchor not in text[start:]:raise ValueError('Extraction anchor not found: '+repr(anchor))
 return text.index(anchor,start)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('source','archive','report'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-instrumented',action='store_true',help='Verify actual Rust ASan imports; Linux mixed profile only');a=p.parse_args();a.report=a.report.resolve()
 if a.rust_instrumented and (sys.platform!='linux' or not a.sanitize):p.error('Mixed instrumentation requires Linux and --sanitize')
 if a.report.exists():p.error('Choose a unique receipt')
 a.report.parent.mkdir(parents=True,exist_ok=True);work=a.report.parent/('timing-'+uuid.uuid4().hex);work.mkdir()
 manifest=ROOT/'migration/patches/coroutine/manifest.json';entries=json.loads(manifest.read_text())['patches']
 bound=[a.archive.resolve(),Path(__file__),Path(__file__).with_suffix('.cc'),Path(__file__).with_name('timing_layout.cc'),manifest,ROOT/'native/coroutine/swoole_rs_coroutine.h',*sorted((ROOT/'crates/coroutine/src').glob('*.rs')),*[manifest.parent/e['path']for e in entries]]
 identities={str(v):digest(v)for v in bound};r=dict(passed=False,full_gate_passed=False,pin=PIN,scope=__doc__,commands=[],results=[],inputs_sha256=identities,native_sanitized=a.sanitize,rust_instrumented=a.rust_instrumented,rust_std_instrumented=False,archive_source_attested_here=False)
 try:
  if a.rust_instrumented:
   imports=subprocess.check_output(['nm','-u',str(a.archive.resolve())],text=True,stderr=subprocess.DEVNULL);r['rust_asan_report_imports']=sorted(set(line.strip()for line in imports.splitlines()if '__asan_report_'in line))
   if not r['rust_asan_report_imports']:raise ValueError('No actual Rust ASan report imports')
  originals={};tree=work/'patched-source'
  for entry in entries:
   for n in entry['upstream_paths']:
    if n not in originals:
     originals[n]=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n],text=True);f=tree/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(originals[n])
  data=subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'include','thirdparty/multipart_parser.h'])
  with tarfile.open(fileobj=io.BytesIO(data)) as archive:
   for member in archive:
    if member.isfile():
     f=tree/member.name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(archive.extractfile(member).read())
  r['patch_proofs']=[apply_patch_verified(tree,manifest.parent/e['path'],e['upstream_paths'],e['sha256'])for e in entries]
  for engine in ('native','selected'):
   folder=work/engine;folder.mkdir();header=originals['include/swoole_coroutine.h']if engine=='native'else(tree/'include/swoole_coroutine.h').read_text();source=originals['src/coroutine/base.cc']if engine=='native'else(tree/'src/coroutine/base.cc').read_text()
   begin=find(header,'    long init_msec =')if engine=='native'else find(header,'#ifdef SWOOLE_RS_COROUTINE\n    static swr_v1_coroutine_timing seed_timing()')
   # Timing members end after execute_usec (and the selected side's #endif); the next member's spelling varies by patch.
   end=find(header,'\n',find(header,'long execute_usec = 0;',begin))+1
   if engine!='native':end=find(header,'#endif\n',end)+len('#endif\n')
   text='class Coroutine {\n'+header[begin:end]+'Context ctx;\npublic:\n'+block(header,'long get_init_msec() const')+'\n'+block(header,'long get_execute_usec() const')+'\nstatic void calc_execute_usec(Coroutine *, Coroutine *);\n};\n'+block(source,'void Coroutine::calc_execute_usec(')+'\n'
   inc=folder/'timing.inc';inc.write_text(text);binary=folder/'timing'
   command=['c++','-std=c++14','-O1','-g','-UNDEBUG','-Wall','-Wextra','-Werror','-I'+str(folder),'-I'+str(ROOT/'native/coroutine'),*(['-DSWOOLE_RS_COROUTINE']if engine=='selected'else[]),str(Path(__file__).with_suffix('.cc')),*([str(a.archive.resolve())]if engine=='selected'else[]),'-lpthread',*(['-ldl','-lm']if sys.platform.startswith('linux')else[]),'-o',str(binary)]
   if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
   for stage,cmd in [('compile',command),('execute',[str(binary)])]:
    require_build_space(work);out=run_isolated(cmd,cwd=folder,timeout=90);r['commands'].append(dict(engine=engine,stage=stage,command=cmd,exit=out.returncode,stdout=out.stdout,stderr=out.stderr));write_report(a.report,r)
    if out.returncode or out.stderr:raise ValueError(engine+' '+stage+' failed or warned')
   r['results'].append(dict(engine=engine,summary=json.loads(out.stdout)))
  r['layout_results']=[]
  # GCC/Clang expose this non-standard-layout SDK's offsets as an extension.
  # Suppress only that diagnostic in this explicit read-only layout witness.
  import shlex
  openssl=shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True))
  for engine in ('native','selected'):
   for standard in ('c++14','c++17'):
    binary=work/(engine+'-'+standard+'-layout')
    command=['c++','-std='+standard,'-Wno-invalid-offsetof','-DSW_CORO_TIME','-DHAVE_EPOLL'if sys.platform.startswith('linux')else'-DHAVE_KQUEUE','-I'+str(tree/'include'),'-I'+str(tree),'-I'+str(ROOT/'native/coroutine'),*openssl,*(['-DSWOOLE_RS_COROUTINE']if engine=='selected'else[]),str(Path(__file__).with_name('timing_layout.cc')),'-o',str(binary)]
    for stage,cmd in [('compile',command),('execute',[str(binary)])]:
     require_build_space(work);out=run_isolated(cmd,cwd=work,timeout=90);r['commands'].append(dict(engine=engine,standard=standard,stage='layout-'+stage,command=cmd,exit=out.returncode,stdout=out.stdout,stderr=out.stderr));write_report(a.report,r)
     if out.returncode or out.stderr:raise ValueError(engine+' layout '+stage+' failed or warned')
    r['layout_results'].append(dict(engine=engine,standard=standard,layout=json.loads(out.stdout)))
  if any(v['layout']!=r['layout_results'][0]['layout']for v in r['layout_results']):raise ValueError('Full SDK layout differs')
  if r['results'][0]['summary']!=r['results'][1]['summary']:raise ValueError('Native/selected observations differ')
  if any(digest(k)!=v for k,v in identities.items()):raise ValueError('Input changed')
  r.update(passed=True,inputs_before_after_equal=True)
 except Exception as e:r['error']=str(e)
 write_report(a.report,r);print(json.dumps({k:r.get(k)for k in ('passed','error','results')}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
