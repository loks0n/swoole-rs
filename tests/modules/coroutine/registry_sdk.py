#!/usr/bin/env python3
"""Compile complete core and PHP/list registry callers with the selected view.
Private copied SDK, no extension load or Coroutine/PHP execution.
"""
import argparse,hashlib,json,subprocess,sys,uuid,shutil,shlex
from pathlib import Path
from ordered_gate import ROOT,PIN
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.private_copy import copy_private
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['source','report']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--sdk-export',type=Path)
 p.add_argument('--private-sdk-report',type=Path,help='Reuse an owned prior completed SDK copy without producer borrow')
 p.add_argument('--producer-path-prefix',type=Path);p.add_argument('--mounted-root',type=Path);a=p.parse_args();a.report=a.report.resolve()
 if bool(a.sdk_export)==bool(a.private_sdk_report):p.error('Require one immutable export or owned private prior SDK report')
 if bool(a.producer_path_prefix)!=bool(a.mounted_root):p.error('Both SDK path mapping options are required together')
 if a.report.exists():p.error('Choose a unique receipt')
 a.report.parent.mkdir(parents=True,exist_ok=True);work=a.report.parent/('registry-sdk-'+uuid.uuid4().hex);work.mkdir();r=dict(passed=False,full_gate_passed=False,scope=__doc__,commands=[],runtime_executed=False,registry_switch_scope='Only REGISTRY_V2 changes; other actual producer features remain fixed')
 try:
  if a.private_sdk_report:
   prior=json.loads(a.private_sdk_report.read_text());r['sdk_source_ref']=prior['sdk_source_ref']
   cpp=next(Path(row['command'][row['command'].index('-c')+1])for row in prior['commands']if row.get('consumer')=='php-list')
   source=cpp.parent.parent
   if not source.is_relative_to(ROOT/'target'):raise ValueError('Private SDK must be an owned held copy under this checkout target')
   original_source=next(str(Path(name).parent)for name in prior['borrowed_inputs_sha256']if Path(name).name=='Makefile')
   original_prefix=original_source+'/../rust-prefix/include'
   # Makefile uses the resolved prefix, not the lexical ../ spelling.
   original_prefix=str(Path(original_prefix).resolve())
   prefix=source.parent/'ffi-include'
   r['private_sdk_scope']='Prior actual configured SDK/old caller body, current verified M06 projection; no fresh producer/source/runtime claim'
  else:
   exported=json.loads(a.sdk_export.read_text());r['sdk_source_ref']=exported['source_ref']
   for name,item in exported['files'].items():
    if sha(a.sdk_export.parent/name)!=item['sha256']:raise ValueError('Changed export '+name)
   manifest_path=Path(exported['files']['build-manifest.json']['source']);
   if a.mounted_root:manifest_path=a.mounted_root/manifest_path.relative_to(a.producer_path_prefix);r['read_only_sdk_mount_mapping']={'recorded':str(a.producer_path_prefix),'mounted':str(a.mounted_root)}
   source=(manifest_path.parent/'src').resolve();manifest=json.loads(manifest_path.read_text())
   if 'phpcoroutines'not in manifest['inputs']['modules'] or 'coroutine'not in manifest['inputs']['modules']:raise ValueError('Real combined M06/M29 SDK required')
   prefix=(source/'../rust-prefix/include').resolve();original_source=str(source);original_prefix=str(prefix)
  bound=[*sorted(source.glob('*.h')),source/'Makefile',source/'ext-src/swoole_coroutine.cc',source/'src/coroutine/base.cc',*sorted((source/'include').rglob('*.h')),*sorted((source/'ext-src').rglob('*.h')),*sorted((source/'thirdparty').rglob('*.h'))];before={str(f):sha(f)for f in bound};r['borrowed_inputs_sha256']=before
  tree=work/'sdk'
  for f in bound:
   q=tree/f.relative_to(source);q.parent.mkdir(parents=True,exist_ok=True);copy_private(f,q)
  prefix_before={str(f):sha(f)for f in prefix.rglob('*.h')};r['borrowed_prefix_headers_sha256']=prefix_before;shutil.copytree(prefix,work/'ffi-include',copy_function=copy_private)
  patchroot=work/'new-coroutine';m=ROOT/'migration/patches/coroutine/manifest.json';entries=json.loads(m.read_text())['patches'];originals={}
  for e in entries:
   for name in e['upstream_paths']:
    if name not in originals:
     originals[name]=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+name]);q=patchroot/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(originals[name])
  r['patch_proofs']=[apply_patch_verified(patchroot,m.parent/e['path'],e['upstream_paths'],e['sha256'])for e in entries]
  for entry in entries:
   for name in entry['upstream_paths']:
    target=tree/name;target.parent.mkdir(parents=True,exist_ok=True);copy_private(patchroot/name,target)
  r['core_source_view']='Current pinned+verified M06 overlay, compiled with actual frozen producer SDK; not a producer-source/runtime claim'
  owned=[Path(__file__),m,*[m.parent/e['path']for e in entries],*sorted((ROOT/'native/coroutine').glob('*.h'))];owned_before={str(f):sha(f)for f in owned};r['owned_inputs_sha256']=owned_before
  includes=shlex.split(next(line.split('=',1)[1]for line in (source/'Makefile').read_text().splitlines()if line.startswith('INCLUDES = ')))
  if a.mounted_root:includes=[part.replace(str(a.producer_path_prefix),str(a.mounted_root))for part in includes]
  includes=[part.replace(original_source,str(tree)).replace(original_prefix,str(work/'ffi-include'))for part in includes]
  cxxflags=shlex.split(next(line.split('=',1)[1]for line in (source/'Makefile').read_text().splitlines()if line.startswith('CXXFLAGS = ')))
  cppflags=shlex.split(next(line.split('=',1)[1]for line in (source/'Makefile').read_text().splitlines()if line.startswith('CPPFLAGS = ')))
  consumers={'core':'src/coroutine/base.cc','php-list':'ext-src/swoole_coroutine.cc'}
  r['profiles']=[dict(consumer=consumer,standard=standard,selected=selected,status='NOTRUN')for consumer in consumers for standard in ['c++14','c++17']for selected in [False,True]]
  expected={'swr_v1_coroutine_registry_'+suffix for suffix in ['selected_insert','find','count','first','item','drop','lookup','print_step']}
  expected_creation={'swr_v1_coroutine_selected_create_step','swr_v1_coroutine_cid_read','swr_v1_coroutine_unregister'}
  r['bridge_assertion_scope']='Actual qualified facade imports selected_insert and selected_create_step, with whole print/lookup/close closure. Frozen7registry signatures/exports remain separately checked by source/C11 ABI controls, not inferred from dead-code imports.'
  for profile in r['profiles']:
    consumer,standard,selected=(profile[k]for k in ['consumer','standard','selected'])
    obj=work/(consumer+'-'+standard+str(selected)+'.o');cmd=['c++',*cxxflags,*cppflags,'-std='+standard,'-Werror','-fPIC','-DENABLE_PHP_SWOOLE','-DZEND_COMPILE_DL_EXT=1','-DHAVE_CONFIG_H','-I'+str(ROOT/'native/coroutine'),*includes,*(['-DSWOOLE_RS_COROUTINE_REGISTRY_V2']if selected else[]),'-MMD','-MF',str(obj)+'.d','-c',str(tree/consumers[consumer]),'-o',str(obj)]
    require_build_space(work);out=run_isolated(cmd,cwd=tree,timeout=120);row=dict(consumer=consumer,standard=standard,selected=selected,command=cmd,exit=out.returncode,stdout=out.stdout,stderr=out.stderr);r['commands'].append(row);profile['status']='FAILED';write_report(a.report,r)
    if out.returncode or out.stderr:
     if 'Coroutine registry ON requires Apple libc++210106 ABI1' in out.stderr:
      r['unsupported_native_order_policy']=True;profile['status']='UNSUPPORTED'
      raise ValueError('Selected registry order policy unsupported; capability remains OFF')
     raise ValueError('Whole consumer failed or warned')
    dep=Path(str(obj)+'.d');names_in_dep=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);dependencies={(Path(name)if Path(name).is_absolute()else tree/name).resolve()for name in names_in_dep}
    staged=(tree/'include/swoole_coroutine.h').resolve();registry_header=(ROOT/'native/coroutine/swoole_rs_coroutine_registry.h').resolve()
    row.update(staged_coroutine_header_used=staged in dependencies,selected_registry_header_used=registry_header in dependencies)
    if staged not in dependencies:raise ValueError('Compiler bypassed staged coroutine header')
    if selected and registry_header not in dependencies:raise ValueError('Compiler bypassed owned selected registry header')
    nm=subprocess.check_output(['nm','-u',str(obj)],text=True,stderr=subprocess.DEVNULL);imports=sorted(set(line.strip()for line in nm.splitlines()if 'swr_v1_coroutine_registry_'in line));row.update(registry_imports=imports)
    names={line.split()[-1].lstrip('_')for line in imports}
    if selected and not imports:raise ValueError('New view absent from actual '+consumer+' caller')
    if selected and consumer=='core'and not expected.issubset(names):raise ValueError('Complete core missing registry bridges: '+','.join(sorted(expected-names)))
    if selected and consumer=='core':
     creation_names={line.split()[-1].lstrip('_')for line in nm.splitlines()if 'swr_v1_coroutine_'in line};row['creation_imports']=sorted(creation_names&expected_creation)
     if not expected_creation.issubset(creation_names):raise ValueError('Whole core missed creation/CID/unregister closure')
    if not selected and imports:raise ValueError('New view leaked into fallback')
    profile['status']='PASS'
  if any(sha(name)!=v for name,v in {**before,**prefix_before}.items()):raise ValueError('Borrowed frozen SDK changed')
  if any(sha(name)!=v for name,v in owned_before.items()):raise ValueError('Owned inputs changed')
  r.update(passed=True,borrowed_inputs_before_after_equal=True,owned_inputs_before_after_equal=True)
 except Exception as e:r['error']=str(e)
 write_report(a.report,r);print(json.dumps({k:r.get(k)for k in ['passed','error','sdk_source_ref']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
