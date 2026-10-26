#!/usr/bin/env python3
"""Four exact ordinary Socket output compositions, positive Native effects only.

Baseline Native, optional corrected Native, Rust and corrected Rust retain their
separate identities. No errors, EINTR, faults, shutdown or lifetime probes run.
Full Socket syntax checks are independent of body-facade execution; neither is
loaded production, original-corpus, performance or whole Socket parity proof.
"""
import argparse,io,json,subprocess,sys,tarfile,tempfile
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated
from tools.harness import run_compiler
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--sanitize',action='store_true');profile=p.add_mutually_exclusive_group();profile.add_argument('--blocking',action='store_true',help='Separate whole blocking send/writev/sendfile/wait positive facade inventory');profile.add_argument('--iov-progress',action='store_true',help='Separate genuine IOVector Native-array progression inventory');profile.add_argument('--ordinary-io',action='store_true',help='Whole ordinary send/recv/peek/vector and one-shot stream positive source controls');profile.add_argument('--socket-policy',action='store_true',help='Whole positive poll/cork/options with exact source error classifier (only error0 executed)');profile.add_argument('--fd-options',action='store_true',help='Whole positive fcntl bit/short-circuit/publication source controls');profile.add_argument('--socket-options',action='store_true',help='Whole normal buffer/timeout/timeval configuration source controls');profile.add_argument('--forwarding',action='store_true',help='Whole file/event forwarding positive source effects; clean Native effects not executed');profile.add_argument('--datagram',action='store_true',help='Whole positive datagram receive/send/wait sequencing; Native sockaddr custody unchanged');profile.add_argument('--connect',action='store_true',help='Whole connect async/sync source policy; inert positive effects only');a=p.parse_args()
if a.report.exists():raise ValueError('Choose a unique receipt path')
fixed=ROOT/'migration/patches/halfclose/0003-send-tls-close-notify.patch'
fixed_sha=next(e['sha256'] for e in json.loads((fixed.parent/'manifest.json').read_text())['patches'] if e['path']==fixed.name)
manifest=ROOT/'migration/patches/reactor/manifest.json';entry=[e for e in json.loads(manifest.read_text())['patches'] if e['upstream_paths']==['src/network/socket.cc']]
if len(entry)!=1:raise ValueError('Expected sole M05 Socket overlay')
entry=entry[0];patch=manifest.parent/entry['path'];dest='src/network/socket.cc'
fixture_name='connect' if a.connect else 'datagram' if a.datagram else 'forwarding' if a.forwarding else 'socket_options' if a.socket_options else 'fd_options' if a.fd_options else 'socket_policy' if a.socket_policy else 'ordinary_io' if a.ordinary_io else 'iov_progress' if a.iov_progress else 'blocking' if a.blocking else 'output'
report=dict(scope=('Whole connect async/sync source orchestration; inert positive effects only, no network/error/interruption/lifetime execution' if a.connect else 'Whole datagram syscall/retry/wait source sequencing; positive modeled effects only, Native address/storage unchanged' if a.datagram else 'Whole file/event forwarding positive source effects; clean syntax/pure Rust only, Native clean unexecuted' if a.forwarding else 'Whole ordinary buffer/timeval/timeout configuration source policy; positive modeled effects only' if a.socket_options else 'Whole ordinary fcntl sequencing/bit/publication source policy, positive effects only' if a.fd_options else 'Whole poll/cork/tcp option source policy with normal positive effects; classifier error0 only, no Native failure/interruption effects' if a.socket_policy else 'Whole ordinary send/recv/peek/vector/read/write source-control policy, positive effects only; no loaded production/error/fault/lifetime qualification' if a.ordinary_io else 'Genuine IOVector complete progression; Native vs Rust-owned descriptor storage, unchanged public class; no kernel/loaded production or error/fault/lifetime qualification' if a.iov_progress else 'Whole blocking Socket orchestration, positive Native effects only; no fault/EINTR/lifetime or loaded production qualification' if a.blocking else __doc__),pin=PIN,patch_application=[],syntax=[],commands=[],results=[],passed=False)
with tempfile.TemporaryDirectory(prefix='swr-output-') as tmp:
 t=Path(tmp)
 try:
  require_build_space(ROOT);require_build_space(t)
  source=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+dest]);original=source.decode()
  headers=subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'include','thirdparty'])
  sdk=t/'sdk'
  with tarfile.open(fileobj=io.BytesIO(headers)) as archive:
   for member in archive:
    if member.isfile():path=sdk/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
  for variant,corrected,selected in [('native',False,False),('native-corrected',True,False),('rust',False,True),('rust-corrected',True,True)]:
   tree=t/variant;file=tree/dest;file.parent.mkdir(parents=True);file.write_bytes(source)
   for overlay,sha in ([(fixed,fixed_sha)] if corrected else [])+([(patch,entry['sha256'])] if selected else []):report['patch_application'].append(dict(variant=variant,proof=apply_patch_verified(tree,overlay,[dest],sha)))
   body=file.read_text()
   # Protected Native effects/optional correction are never converted or tested
   # by interruption: attest their exact text/order in each selected composition.
   shutdown=lambda text:block(text,text.index('bool Socket::ssl_shutdown('))[0]
   control=t/('native-corrected' if corrected else 'native')/dest
   if selected and shutdown(body)!=shutdown(control.read_text()):raise ValueError('Protected SSL shutdown changed')
   prefix='    size_t sendn = get_sendfile_chunk_size(task->begin, task->end);\n    ssize_t rv = sendfile(task->file, &task->begin, sendn);\n'
   if corrected:prefix+='    if (rv < 0 && errno == EINTR) {\n        return SW_OK;\n    }\n'
   prefix+='\n    swoole_trace("rv=%ld|begin=%ld|sendn=%lu|end=%lu", rv, (long) task->begin, sendn, task->end);'
   if prefix not in body:raise ValueError('Native sendfile prefix changed')
   for ssl in [False,True]:
    command=['c++','-std=c++14','-fsyntax-only','-I'+str(sdk/'include'),'-I'+str(sdk),'-I'+str(ROOT/'native/reactor'),*subprocess.check_output(['pkg-config','--cflags','openssl'],text=True).split()]
    if selected:command+=['-DSWOOLE_RS_REACTOR']
    if ssl:command+=['-DSW_USE_OPENSSL']
    command+=[str(file)];result=run_isolated(command,cwd=t,timeout=60)
    report['syntax'].append(dict(variant=variant,ssl=ssl,command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if result.returncode or result.stderr:raise RuntimeError(variant+' full Socket syntax failed/warned')
   if selected:
    disabled=[x for x in command if x!='-DSWOOLE_RS_REACTOR'];result=run_isolated(disabled,cwd=t,timeout=60)
    refused=result.returncode!=0 and 'Reactor overlay requires --enable-swoole-rs-reactor' in result.stderr
    report['syntax'].append(dict(variant=variant+'-disabled',command=disabled,exit=result.returncode,stderr=result.stderr,expected_refusal=refused))
    if not refused:raise RuntimeError('Disabled selected Socket not refused')
   extracted='\n'.join(block(body,body.index(sig))[0] for sig in ['static bool check_sendfile_parameters(','static size_t get_sendfile_chunk_size(','int Socket::handle_sendfile(','int Socket::handle_send()','static void Socket_sendfile_destructor(','int Socket::sendfile_async('])
   if a.blocking:
    macro=body[body.index('#define CHECK_RETURN_VALUE'):body.index('bool Socket::wait_for(')]
    timer=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':include/swoole_timer.h'],text=True)
    conversion=block(timer,timer.index('static inline long sec2msec(const double'))[0]
    extracted=macro+'\n'+conversion+'\n'+'\n'.join(block(body,body.index(sig))[0] for sig in ['static bool check_sendfile_parameters(','static size_t get_sendfile_chunk_size(','int Socket::what_event_want(','bool Socket::wait_for('])+'\n'
    if selected:extracted+=block(body,body.index('template<class Effect>'))[0]+'\n'
    extracted+='\n'.join(block(body,body.index(sig))[0] for sig in ['int Socket::sendfile_sync(','ssize_t Socket::writev_sync(','ssize_t Socket::send_sync(','ssize_t Socket::recv_sync('])
   if a.iov_progress:
    header=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':include/swoole_socket.h'],text=True)
    declaration=block(header,header.index('struct IOVector {'))[0]+';'
    extracted=declaration+'\n'+'\n'.join(block(body,body.index(sig))[0] for sig in ['IOVector::IOVector(','IOVector::~IOVector(','void IOVector::update_iterator('])
   if a.ordinary_io:
    timer=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':include/swoole_timer.h'],text=True)
    conversion=block(timer,timer.index('static inline long sec2msec(const double'))[0]
    macro=body[body.index('#define CHECK_RETURN_VALUE'):body.index('bool Socket::wait_for(')]
    extracted=macro+'\n'+conversion+'\n'
    if selected:extracted+=block(body,body.index('template<class Effect>'))[0]+'\n'
    extracted+='\n'.join(block(body,body.index(sig))[0] for sig in ['ssize_t Socket::recv(','ssize_t Socket::send(','ssize_t Socket::peek(','ssize_t Socket::readv(','ssize_t Socket::writev(','ssize_t Socket::read_sync(','ssize_t Socket::write_sync('])
   if a.socket_policy:
    extracted='\n'.join(block(body,body.index(sig))[0] for sig in ['int Socket::wait_event(','int Socket::catch_error(','bool Socket::cork(','bool Socket::uncork(','int Socket::set_tcp_nopush(','bool Socket::set_tcp_nodelay('])
   if a.fd_options:
    extracted='\n'.join(block(body,body.index(sig))[0] for sig in ['static bool _fcntl_set_option(','bool Socket::set_fd_option('])
   if a.socket_options:
    extracted='\n'.join(block(body,body.index(sig))[0] for sig in ['bool Socket::set_buffer_size(','bool Socket::set_recv_buffer_size(','bool Socket::set_send_buffer_size(','static bool _set_timeout(','void Socket::set_timeout(','double Socket::get_timeout(','bool Socket::has_timedout(','bool Socket::set_kernel_read_timeout(','bool Socket::set_kernel_write_timeout('])
   if a.forwarding:
    extracted='\n'.join(block(body,body.index(sig))[0] for sig in ['ssize_t Socket::sendfile(','ssize_t Socket::send_async(','void Socket::clean(','bool Socket::check_liveness('])
   if a.datagram:
    timer=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':include/swoole_timer.h'],text=True)
    conversion=block(timer,timer.index('static inline long sec2msec(const double'))[0]
    macro=body[body.index('#define CHECK_RETURN_VALUE'):body.index('bool Socket::wait_for(')]
    extracted=macro+'\n'+conversion+'\n'
    if selected:extracted+=block(body,body.index('template<class Effect>'))[0]+'\n'
    signatures=['ssize_t Socket::sendto_sync(','ssize_t Socket::recvfrom(char *buf','ssize_t Socket::recvfrom_sync(char *buf, size_t len, int flags, Address *sa)','ssize_t Socket::recvfrom_sync(char *buf, size_t len, int flags, sockaddr *addr']
    extracted+='\n'.join(block(body,body.index(sig))[0] for sig in signatures)
    wrapper=signatures[2]
    if block(body,body.index(wrapper))[0]!=block(original,original.index(wrapper))[0]:raise ValueError('Native Address forwarding changed')
   if a.connect:
    timer=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':include/swoole_timer.h'],text=True)
    conversion=block(timer,timer.index('static inline long sec2msec(const double'))[0]
    extracted=conversion+'\n'+block(body,body.index('swReturnCode Socket::connect_async('))[0]+'\n#define connect_async fixture_connect_async\n'+block(body,body.index('int Socket::connect_sync('))[0]+'\n#undef connect_async\n'
    report['connect_sync_callee_adapter']='Only sync body calls fixture_connect_async normal READY/WAIT source fact; real async body separately uses inert successful connect. No Native negative errno/effect path executes.'
   (tree/(fixture_name+'.inc')).write_text(extracted);binary=tree/'consumer';command=['c++','-std=c++14','-O1','-g','-I'+str(tree),'-I'+str(ROOT/'native/reactor'),str(ROOT/('tests/modules/reactor/'+fixture_name+'.cc')),str(a.archive.resolve()),'-lpthread','-o',str(binary)]
   if a.sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
   if sys.platform.startswith('linux'):command+=['-ldl','-lm']
   for stage,cmd in [('compile',command),('execute',[str(binary)])]:
    require_build_space(ROOT);require_build_space(t)
    result=run_compiler(cmd, timeout=60) if stage=='compile' else vars(run_isolated(cmd,cwd=t,timeout=60))
    report['commands'].append(dict(variant=variant,stage=stage,command=cmd,exit=result['returncode'],stdout=result['stdout'],stderr=result['stderr'],cache={k:result[k] for k in ['cache_hit','cache_key','cache_reason'] if k in result}))
    if result['returncode'] or result['stderr']:raise RuntimeError(variant+' '+stage+' failed/warned')
   report['results'].append(dict(variant=variant,observations=json.loads(result['stdout'])))
  if len({json.dumps(row['observations'],sort_keys=True) for row in report['results']})!=1:raise RuntimeError('Four positive observations differ')
  report['passed']=True
 except Exception as error:report['error']=str(error)
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['passed','error','results']}));raise SystemExit(not report['passed'])
