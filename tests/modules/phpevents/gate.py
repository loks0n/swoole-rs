#!/usr/bin/env python3
"""Pinned complete ordinary Event bodies and real Rust metadata, modeled native APIs; no runtime/fault/IPC proof."""
import argparse,hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report
from tools.build_upstream import COMMIT as PIN
DESTINATION='ext-src/swoole_event.cc'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def body(text,signature):
    start=text.index(signature);end=text.index('{',start)+1;depth=1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
def stage(source,work):
    # git requires an absolute ceiling even for callers using relative scratch.
    work=work.resolve()
    manifest=json.loads((ROOT/'migration/patches/phpevents/manifest.json').read_text())
    if manifest['upstream_commit'] != PIN:raise ValueError('Overlay pin mismatch')
    original=subprocess.check_output(['git','-C',str(source),'show',PIN+':'+DESTINATION])
    target=work/DESTINATION;target.parent.mkdir(parents=True);target.write_bytes(original)
    environment={**os.environ,'GIT_CEILING_DIRECTORIES':str(work.parent)}
    for entry in manifest['patches']:
        patch=ROOT/'migration/patches/phpevents'/entry['path']
        if entry['upstream_paths']!=[DESTINATION] or sha(patch)!=entry['sha256']:raise ValueError('Overlay identity/destination mismatch')
        if not patch.read_text().startswith('diff --git a/'+DESTINATION+' b/'+DESTINATION+'\n'):raise ValueError('Missing complete overlay envelope')
        for check in [['--check'],[]]:subprocess.run(['git','apply',*check,str(patch)],cwd=work,env=environment,check=True,capture_output=True)
    return original.decode(),target.read_text()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-sanitize',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.rust_sanitize and not a.sanitize:p.error('--rust-sanitize requires --sanitize')
    output=a.output.resolve();work=output.parent/('phpevents-'+uuid.uuid4().hex);work.mkdir(parents=True)
    report={'passed':False,'scope':__doc__,'pin':PIN,'work':str(work),'commands':[],'measurement_performed':False,'native_runtime_executed':False,'results':[],'native_sanitizers':['address','undefined'] if a.sanitize else [],'rust_sanitized':False}
    def checkpoint():write_report(output,report)
    def run(command,environment=None):
        require_build_space(ROOT);r=run_isolated(list(map(str,command)),timeout=90,**({'env':environment} if environment else {}));report['commands'].append(dict(command=list(map(str,command)),exit=r.returncode,stdout=r.stdout,stderr=r.stderr));checkpoint();return r
    try:
        require_build_space(ROOT);original,selected=stage(a.source,work)
        start = 'static const zend_function_entry swoole_event_methods[]'
        reference = original[original.index(start):original.index('// clang-format on', original.index(start))]
        if '#else\n' + reference + '#endif\n' not in selected:
            raise ValueError('Original complete Native method-table fallback changed')
        signatures=['void php_swoole_event_minit(int module_number) {','int php_swoole_convert_to_fd(zval *zsocket) {','static PHP_FUNCTION(swoole_event_add) {','int php_swoole_convert_to_fd_ex(zval *zsocket, int *async) {','static Socket *event_get_socket(int socket_fd) {','static PHP_FUNCTION(swoole_event_set) {','static PHP_FUNCTION(swoole_event_isset) {','static PHP_FUNCTION(swoole_event_write) {','static PHP_FUNCTION(swoole_event_del) {','static int event_readable_callback(Reactor *reactor, Event *event) {','static int event_writable_callback(Reactor *reactor, Event *event) {','static void event_cycle_callback(void *data) {','static PHP_FUNCTION(swoole_event_cycle) {']
        for engine,text in [('reference',original),('candidate',selected)]:
            parts=[text[text.index('// clang-format off'):text.index('void php_swoole_event_minit(')]]+([text[text.index('// M28 sole registry adapter:'):text.index('// End M28 sole registry adapter.')],body(text,'static uint32_t phpevents_fd_kind(')] if engine=='candidate' else [])+([body(text, 'struct EventObject {') + ';'] if engine == 'candidate' else [])+[body(text,s).replace('Reactor *reactor, Event *event', '[[maybe_unused]] Reactor *reactor, Event *event',1) for s in signatures]
            # Only fixture declarations annotate the upstream-unused reactor
            # parameter; bodies/ABI types and strict -Wextra/-Werror stay intact.
            report['fixture_declaration_annotation']='[[maybe_unused]] on original unused Reactor parameter in read/write callback declarations; actual SDK source unmodified.'
            (work/(engine+'.inc')).write_text('\n'.join(parts)+'\n')
        archive=work/'libphpevents.a';command=['rustc','--edition=2024','--crate-type=staticlib','-C','opt-level=2','-D','warnings',ROOT/'crates/phpevents/src/lib.rs','-o',archive]
        if a.rust_sanitize:command+=['-Zsanitizer=address','-C','panic=abort']
        if run(command,{**os.environ,'RUSTC_BOOTSTRAP':'1'} if a.rust_sanitize else None).returncode:raise ValueError('Rust policy compilation failed')
        if not a.sanitize:
            # Actual C11 source links through the C++14 driver to the same archive.
            abi_object=work/'callback-pair-c11.o';abi_binary=work/'callback-pair-c11'
            if run(['cc','-std=c11','-O2','-UNDEBUG','-Wall','-Wextra','-Werror',
                    '-I'+str(ROOT/'native/phpevents'),'-c',Path(__file__).with_name('callback_pair_abi.c'),'-o',abi_object]).returncode:
                raise ValueError('Callback pair C11 ABI compilation failed')
            abi_link=['c++','-std=c++14',abi_object,archive,'-lpthread','-lm','-o',abi_binary]
            if sys.platform.startswith('linux'):abi_link+=['-ldl','-lrt','-lutil']
            if run(abi_link).returncode or run([abi_binary]).returncode:
                raise ValueError('Callback pair C11/C++14 inert linkage failed')
            report['callback_pair_c11_cpp14']={'passed':True}
        if a.rust_sanitize:
            members=subprocess.check_output(['ar','t',str(archive)],text=True).splitlines()
            own=[name for name in members if name.startswith('libphpevents.lib.') and name.endswith('.rcgu.o')]
            if not own:raise ValueError('Rust module object missing from archive')
            inspected=[]
            for index,member in enumerate(own):
                obj=work/('instrumentation-'+str(index)+'.o')
                obj.write_bytes(subprocess.check_output(['ar','p',str(archive),member]))
                symbols=subprocess.check_output(['nm','-u',str(obj)],text=True,stderr=subprocess.PIPE)
                inspected.append(dict(member=member,asan_load_store_imports='__asan_report_' in symbols))
            report['rust_instrumentation']=inspected
            if not any(item['asan_load_store_imports'] for item in inspected):raise ValueError('Rust module has no ASan load/store imports')
            report['rust_sanitized']=True
        for sockets in [False,True]:
            binary=work/('ordinary-'+str(sockets));command=['c++','-std=c++17','-O2','-UNDEBUG','-Wall','-Wextra','-Werror','-DSWOOLE_RS_PHPEVENTS','-I'+str(work),'-I'+str(ROOT/'native/phpevents'),Path(__file__).with_name('ordinary.cc'),archive,'-lpthread','-lm','-o',binary]
            if sockets:command+=['-DSWOOLE_SOCKETS_SUPPORT']
            if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
            if run(command).returncode:raise ValueError('Actual ordinary body fixture compilation failed; sockets='+str(sockets))
            result=run([binary]);row={'sockets':sockets,'exit':result.returncode,'passed':False};report['results'].append(row)
            if result.returncode:raise ValueError('Ordinary modeled comparison failed')
            row['summary']=json.loads(result.stdout);row['passed']=True
        report['passed']=True
    except Exception as error:report['error']=str(error)
    checkpoint();print(json.dumps({k:report.get(k) for k in ['passed','error','work']}));return int(not report['passed'])
if __name__=='__main__':sys.exit(main())
