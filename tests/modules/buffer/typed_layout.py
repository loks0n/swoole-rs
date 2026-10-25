#!/usr/bin/env python3
"""Compile the patched Buffer header with SWOOLE_RS_BUFFER_TYPED omitted/0/1 and check its layout."""
import argparse,io,json,subprocess,sys,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import COMMIT as PIN
def carrier(text):
 start=text.index('class Buffer {');depth=0
 for i in range(text.index('{',start),len(text)):
  if text[i]=='{':depth+=1
  elif text[i]=='}':
   depth-=1
   if depth==0:return text[start:i+1]
 raise ValueError('Missing complete Buffer declaration')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 report=dict(pin=PIN,rows=[])
 with tempfile.TemporaryDirectory(prefix='swr-buffer-layout-') as tmp:
  tree=Path(tmp);data=subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'include'])
  with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
   for member in bundle:
    if member.isfile():
     out=tree/member.name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(bundle.extractfile(member).read())
  manifest=ROOT/'migration/patches/buffer/manifest.json';entry=json.loads(manifest.read_text())['patches'][0]
  apply_patch_verified(tree,manifest.parent/entry['path'],entry['upstream_paths'],entry['sha256'])
  for standard in ['c++14','c++17','c++20']:
   declarations={}
   for enabled in [None,0,1]:
    size=8 if enabled==1 else 56
    text='#include "swoole.h"\n#include "swoole_buffer.h"\n#include <type_traits>\nstatic_assert(sizeof(swoole::Buffer)=='+str(size)+',"Buffer carrier");\nstatic_assert(sizeof(swoole::BufferChunk)==40 && alignof(swoole::BufferChunk)==8,"Public Chunk");\nstatic_assert(offsetof(swoole::BufferChunk,length)==8 && offsetof(swoole::BufferChunk,offset)==12 && offsetof(swoole::BufferChunk,value)==16 && offsetof(swoole::BufferChunk,destroy)==32,"Frozen Chunk fields");\n'
    command=['c++','-std='+standard,'-DSWOOLE_RS_BUFFER=1','-I'+str(tree/'include'),'-I'+str(ROOT/'native/include'),'-I'+str(ROOT/'native/buffer')]
    if enabled is not None:command+=['-DSWOOLE_RS_BUFFER_TYPED='+str(enabled)]
    result=subprocess.run(command+['-fsyntax-only','-x','c++','-'],input=text,capture_output=True,text=True)
    report['rows'].append(dict(standard=standard,macro=enabled,buffer_size=size,returncode=result.returncode,stderr=result.stderr,passed=result.returncode==0))
    if result.returncode:continue
    pp=subprocess.run(command+['-E','-P','-x','c++','-'],input=text,capture_output=True,text=True);assert pp.returncode==0,pp.stderr
    declarations[enabled]=carrier(pp.stdout)
   if None in declarations and 0 in declarations and declarations[None]!=declarations[0]:
    report['rows'].append(dict(standard=standard,check='omitted equals explicit zero',passed=False))
 report['passed']=all(r['passed'] for r in report['rows'])
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 return int(not report['passed'])
if __name__=='__main__':raise SystemExit(main())
