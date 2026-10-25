#!/usr/bin/env python3
"""Project complete coupled Coroutine status into the current reserved overlays."""
from pathlib import Path
import argparse, difflib, hashlib, json, subprocess, sys, tempfile
from ordered_gate import ROOT, PIN, block
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
manifest_path=ROOT/'migration/patches/coroutine/manifest.json';manifest=json.loads(manifest_path.read_text())
with tempfile.TemporaryDirectory(prefix='swr-coroutine-status-source-') as temporary:
 tree=Path(temporary)
 for entry in manifest['patches']:
  for name in entry['upstream_paths']:
   target=tree/name
   if not target.exists():
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+name]))
  apply_patch_verified(tree,manifest_path.parent/entry['path'],entry['upstream_paths'],entry['sha256'])
 hn='include/swoole_coroutine.h';sn='src/coroutine/base.cc';header=(tree/hn).read_text();source=(tree/sn).read_text()
 if 'swr_v1_coroutine_status status_' not in header:
  old='    enum State state = STATE_INIT;\n    enum ResumeCode resume_code_ = RC_OK;';assert header.count(old)==1
  header=header.replace(old,'''#ifdef SWOOLE_RS_COROUTINE
    swr_v1_coroutine_status status_ = {STATE_INIT, RC_OK};
#else
'''+old+'\n#endif')
  marker='    typedef void (*SwapCallback)(void *);'
  header=header.replace(marker,'''#ifdef SWOOLE_RS_COROUTINE
    static_assert(sizeof(State) == 4 && alignof(State) == 4 && sizeof(ResumeCode) == 4 && alignof(ResumeCode) == 4,
                  "Coroutine lifecycle requires qualified Native enum ABI");
#endif
'''+marker,1)
  methods={'enum State get_state() const':'return static_cast<State>(swr_v1_coroutine_status_read(&status_).state);','bool is_canceled() const':'return swr_v1_coroutine_status_read(&status_).canceled;','bool is_timedout() const':'return swr_v1_coroutine_status_read(&status_).timedout;','bool is_suspending() const':'return swr_v1_coroutine_status_read(&status_).suspending;'}
  for signature,selected in methods.items():
   original=block(header,signature);inside=original[original.index('{')+1:-1]
   header=header.replace(original,original[:original.index('{')+1]+'\n#ifdef SWOOLE_RS_COROUTINE\n        '+selected+'\n#else'+inside+'#endif\n    }',1)
  marker='namespace swoole {\n'
  guard='''#ifdef SWOOLE_RS_COROUTINE
static_assert(sizeof(swr_v1_coroutine_status) == 8 && alignof(swr_v1_coroutine_status) == 4 &&
              offsetof(swr_v1_coroutine_status, state) == 0 && offsetof(swr_v1_coroutine_status, code) == 4,
              "Coroutine status requires qualified adjacent int32 ABI");
#endif
'''
  assert marker in header;header=header.replace(marker,guard+marker,1)
  def change(signature,op,stage):
   global source
   old=block(source,signature);new=old.replace('swr_v1_coroutine_transition('+op+',','swr_v1_coroutine_status_transition(&status_, '+op+',').replace(', resume_code_)',', '+stage+')')
   source=source.replace(old,new,1)
  for sig,op,stage in [('void Coroutine::check_end()','SWR_CO_CHECK_END','SWR_CO_STATUS_DECIDE'),('void Coroutine::yield()','SWR_CO_YIELD','SWR_CO_STATUS_PUBLISH'),('void Coroutine::resume()','SWR_CO_RESUME','SWR_CO_STATUS_PUBLISH'),('bool Coroutine::cancel()','SWR_CO_CANCEL','SWR_CO_STATUS_DECIDE'),('void Coroutine::close()','SWR_CO_CLOSE','SWR_CO_STATUS_PUBLISH')]:change(sig,op,stage)
  for op in ['SWR_CO_WAIT_BEFORE_DELETE','SWR_CO_WAIT_AFTER_DELETE']:change('bool Coroutine::yield_ex(',op,'SWR_CO_STATUS_DECIDE')
  old='    const auto plan = swr_v1_coroutine_transition(SWR_CO_RUN, 0, resume_code_);\n';assert source.count(old)==1;source=source.replace(old,'')
  signature='long Coroutine::run()';old=block(source,signature);new=old.replace('    state = static_cast<State>(plan.state);','    swr_v1_coroutine_status_transition(&status_, SWR_CO_RUN, 0, SWR_CO_STATUS_PUBLISH);');assert new!=old;source=source.replace(old,new,1)
  for old in ['    state = static_cast<State>(plan.state);\n','    resume_code_ = static_cast<ResumeCode>(plan.resume_code);\n']:
   # CANCEL has its own delayed publication after Native function copy and clear.
   if 'resume_code_' in old:
    cancel=block(source,'bool Coroutine::cancel()');new=cancel.replace(old,'    swr_v1_coroutine_status_transition(&status_, SWR_CO_CANCEL, SWR_CO_CANCELABLE, SWR_CO_STATUS_PUBLISH);\n');assert new!=cancel;source=source.replace(cancel,new,1)
   source=source.replace(old,'')
  old='        resume_code_ = RC_TIMEDOUT;';assert source.count(old)==1;source=source.replace(old,'        swr_v1_coroutine_status_transition(&status_, SWR_CO_STATUS_TIMEOUT, 0, SWR_CO_STATUS_PUBLISH);')
  assert source.count('switch (coroutine.second->state)')==1;source=source.replace('switch (coroutine.second->state)','switch (coroutine.second->get_state())')
 assert 'resume_code_' not in source
 (tree/hn).write_text(header);(tree/sn).write_text(source)
 for entry in manifest['patches']:
  if not any(name in [hn,sn] for name in entry['upstream_paths']):continue
  output=''
  for name in entry['upstream_paths']:
   reference=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+name],text=True)
   output+='diff --git a/'+name+' b/'+name+'\n'+''.join(difflib.unified_diff(reference.splitlines(True),(tree/name).read_text().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
  output=''.join('\n' if line==' \n' else line for line in output.splitlines(True));patch=manifest_path.parent/entry['path'];patch.write_text(output);entry['sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
 manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
