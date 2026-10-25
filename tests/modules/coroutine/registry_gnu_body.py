#!/usr/bin/env python3
"""Captured GNU body oracle versus explicit GNU policy in production Rust APIs.
Host inert metadata only, not installed GNU/Linux, allocator or runtime parity.
"""
import argparse,hashlib,json,sys,uuid,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--oracle-dir',type=Path,required=True);p.add_argument('--candidate-dir',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--native-sanitize',action='store_true');a=p.parse_args();a.report=a.report.resolve()
 if a.report.exists():p.error('Choose a unique receipt')
 work=a.report.parent/('registry-gnu-body-'+uuid.uuid4().hex);work.mkdir(parents=True)
 paths=[ROOT/'crates/coroutine/src/lib.rs',ROOT/'native/coroutine/swoole_rs_coroutine_registry.h',Path(__file__),Path(__file__).with_suffix('.cc'),a.oracle_dir/'actual-gnu.inc',a.oracle_dir/'source-proof.json'];before={str(x):sha(x)for x in paths};helper=Path(__file__).with_name('registry_gnu_source.py');before[str(helper)]=sha(helper)
 before.update({str(p):sha(p) for p in [*(ROOT/'crates/coroutine/src').glob('*.rs'),*(ROOT/'native/coroutine').glob('*.h')]})
 r=dict(passed=False,scope=__doc__,work=str(work),inputs_sha256=before,commands=[],results=[],native_linux_qualified=False,production_archive_used=False,rust_instrumented=False,native_cpp_sanitized=a.native_sanitize,allocator_effects_modeled=False,activation=False)
 def run(cmd):
  require_build_space(work);o=run_isolated(list(map(str,cmd)),cwd=work,timeout=120);r['commands'].append(dict(command=list(map(str,cmd)),exit=o.returncode,stdout=o.stdout,stderr=o.stderr));write_report(a.report,r)
  if o.returncode or o.stderr:raise ValueError('Required command failed or warned')
  return o.stdout
 try:
  proof=json.loads(paths[-1].read_text());oracle=paths[-2].read_text()
  captured=[]
  for name,expected in proof['input_sha256'].items():
   path=a.candidate_dir/name
   if sha(path)!=expected:raise ValueError('Official captured source changed: '+name)
   before[str(path)]=expected;captured.append(path.read_text())
  for name,value in proof['source_bodies'].items():
   if hashlib.sha256(value.encode()).hexdigest()!=proof['source_bodies_sha256'][name]or value not in oracle or not any(value in text for text in captured):raise ValueError('Captured body missing/changed: '+name)
  from registry_gnu_source import body
  header=(a.candidate_dir/'candidate-headers/usr/include/c++/12/bits/hashtable.h').read_text()
  policy=(a.candidate_dir/'mirror-hashtable_c++0x.cc').read_text()
  definitions={'insert_bucket':body(header,'_M_insert_bucket_begin(size_type __bkt, __node_ptr __node)\n'),
    'unique_rehash':body(header,'_M_rehash_aux(size_type __bkt_count, true_type'),
    'next_bucket':body(policy,'_Prime_rehash_policy::_M_next_bkt'),
    'need_rehash':body(policy,'_M_need_rehash(std::size_t __n_bkt'),
    'clear':body(header,'clear() noexcept\n')}
  for name,value in definitions.items():
   if value[value.index('{'):]!=proof['source_bodies'][name]:raise ValueError('Independent definition extractors differ: '+name)
  r['independent_definition_bindings_equal']=True
  r['source_proof']=proof;shutil.copy2(paths[-2],work/'actual-gnu.inc')
  r['production_source_unmodified']=True
  archive=work/'libregistry.a';run(['rustc','--edition=2024','--crate-type=staticlib','--crate-name=coroutine_registry','-C','opt-level=2','-D','warnings',paths[0],'-o',archive])
  for standard in ['c++14','c++17']:
   for opt in ['-O0','-O2']:
    exe=work/(standard+opt);cmd=['c++','-std='+standard,opt,'-g','-UNDEBUG','-Wall','-Wextra','-Werror','-DSWOOLE_RS_COROUTINE_REGISTRY_V2=1','-I'+str(ROOT/'native/coroutine'),'-I'+str(work),paths[3],archive,'-lpthread','-lm','-o',exe]
    if a.native_sanitize:cmd+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
    run(cmd);result=run([exe]);r['results'].append(dict(standard=standard,opt=opt,summary=json.loads(result)))
  if any(sha(Path(k))!=v for k,v in before.items()):raise ValueError('Owned/borrowed inputs changed')
  r['passed']=True
 except Exception as e:r['error']=str(e)
 write_report(a.report,r);print(json.dumps({k:r.get(k)for k in ['passed','error','work']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
