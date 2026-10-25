#!/usr/bin/env python3
"""Typed queue/facade positive source gate; no Socket/network or callback probes."""
import shutil
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import COMMIT as PIN
def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--sanitize', action='store_true')
    a = p.parse_args()
    if min(shutil.disk_usage(ROOT).free, shutil.disk_usage(tempfile.gettempdir()).free) < 4*1024**3: p.error("4GiB disk guard refused compilation")
    if a.report.exists(): p.error('Refusing to overwrite an existing receipt')
    report = dict(pin=PIN, scope=__doc__, rows=[])
    with tempfile.TemporaryDirectory(prefix='swr-buffer-typed-') as tmp:
        tree = Path(tmp)
        data = subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'include','src/core/buffer.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    dest = tree/member.name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(archive.extractfile(member).read())
        manifest=ROOT/'migration/patches/buffer/manifest.json'
        report['patches']=[apply_patch_verified(tree,manifest.parent/e['path'],e['upstream_paths'],e['sha256']) for e in json.loads(manifest.read_text())['patches'][:2]]
        for standard in ['c++14','c++17','c++20']:
            binary=tree/standard
            command=['c++','-std='+standard,'-O1','-g','-DSWOOLE_RS_BUFFER=1','-DSWOOLE_RS_BUFFER_TYPED=1','-I'+str(tree/'include'),'-I'+str(ROOT/'native/include'),'-I'+str(ROOT/'native/buffer'),str(tree/'src/core/buffer.cc'),str(ROOT/'tests/modules/buffer/typed.cc'),str(a.archive.resolve()),'-lpthread','-o',str(binary)]
            if a.sanitize: command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            if sys.platform.startswith('linux'): command+=['-ldl','-lm']
            compiled=subprocess.run(command,capture_output=True,text=True)
            row=dict(command=command,compile_returncode=compiled.returncode,compile_stdout=compiled.stdout,compile_stderr=compiled.stderr)
            if compiled.returncode==0:
                run=subprocess.run([str(binary)],capture_output=True,text=True)
                row.update(returncode=run.returncode,stdout=run.stdout,stderr=run.stderr)
                if run.returncode==0: row['outcome']=json.loads(run.stdout)
            row['passed']=compiled.returncode==0 and row.get('returncode')==0
            report['rows'].append(row)
    report['passed']=all(r['passed'] for r in report['rows'])
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    return int(not report['passed'])
if __name__=='__main__': raise SystemExit(main())
