#!/usr/bin/env python3
"""Complete pinned/selected add/set/del bodies with positive Native effect facades.

Poll/kqueue both hosts; actual target epoll mask and control body on Linux only.
No native error/fault, allocation, callback, fd-reuse or lifetime probe execution.
Not actual kernel/Socket production or whole-module parity qualification.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ordered_gate import ROOT,PIN,block, apply_patch_verified
from poll_snapshot import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args()
    manifest=ROOT/'migration/patches/reactor/manifest.json';entries=json.loads(manifest.read_text())['patches']
    originals={}
    with tempfile.TemporaryDirectory(prefix='swr-registration-') as temporary:
        tree=Path(temporary)
        for entry in entries:
            for name in entry['upstream_paths']:
                path=tree/name
                if not path.exists():
                    path.parent.mkdir(parents=True,exist_ok=True)
                    content=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+name])
                    path.write_bytes(content);originals[name]=content.decode()
        patches=[]
        for entry in entries:
            patch=manifest.parent/entry['path']
            if digest(patch)!=entry['sha256']:raise ValueError('Overlay checksum mismatch')
            application = apply_patch_verified(tree, patch, entry['upstream_paths'], entry['sha256'])
            patches.append(dict(path=entry['path'],application=application))
        fragments=[]
        for backend in ['poll','kqueue',*(['epoll'] if sys.platform.startswith('linux') else [])]:
            original_type={'poll':'ReactorPoll','epoll':'ReactorEpoll','kqueue':'ReactorKqueue'}[backend]
            path='src/reactor/'+backend+'.cc'
            selected=(tree/path).read_text()
            for label,text in [('Original',originals[path]),('Selected',selected)]:
                name=backend.capitalize()+label
                methods=[]
                if backend=='epoll':
                    methods.append(block(text,text.index('static int get_events('))[0])
                for method in ['add','set','del']:
                    body,_=block(text,text.index('int '+original_type+'::'+method+'('))
                    body=body.replace(original_type+'::','').replace('struct kevent','struct FakeKevent').replace('::kevent(','native_kevent(').replace('epoll_ctl(','native_epoll_ctl(').replace('EV_SET(','TEST_EV_SET(')
                    methods.append(body)
                fragments.append('struct '+name+' : RegistrationBase { using RegistrationBase::RegistrationBase;\n'+'\n'.join(methods)+'\n};')
        (tree/'registration.inc').write_text('\n'.join(fragments))
        binary=tree/'registration'
        command=['c++','-std=c++14','-O1','-g','-I'+str(tree),'-I'+str(ROOT/'native/reactor'),str(ROOT/'tests/modules/reactor/registration.cc'),str(args.archive.resolve()),'-lpthread','-o',str(binary)]
        if args.sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        if sys.platform.startswith('linux'):command+=['-ldl','-lm']
        result=subprocess.run(command,capture_output=True,text=True)
        report=dict(pin=PIN,scope=__doc__,patches=patches,command=command,compile_returncode=result.returncode,compile_stdout=result.stdout,compile_stderr=result.stderr)
        if result.returncode==0:
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            report.update(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
            if result.returncode==0:report['observations']=json.loads(result.stdout)
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({key:report[key] for key in ['compile_returncode','observations'] if key in report}))
        return result.returncode


if __name__=='__main__':raise SystemExit(main())
