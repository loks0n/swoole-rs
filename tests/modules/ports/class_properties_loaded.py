#!/usr/bin/env python3
"""Actual immutable native/selected PHP Port class declarations; reflection only, no objects/IO/callbacks/lifetime probes."""
from pathlib import Path
import argparse,json,subprocess,hashlib,sys,re
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--selected',type=Path,required=True);p.add_argument('--php',default='php');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('Refusing an existing receipt')
 raw=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':ext-src/swoole_server_port.cc'],text=True);start=raw.index('void php_swoole_server_port_minit(');end=raw.index('\n}',start);expected=[]
 for kind,name,tail in re.findall(r'zend_declare_property_(null|long|bool)\(swoole_server_port_ce, ZEND_STRL\("([^"]+)"\), ([^;]+)\);',raw[start:end]):
  private='ZEND_ACC_PRIVATE'in tail;value=None if kind=='null'else bool(int(tail.split(',')[0]))if kind=='bool'else int(tail.split(',')[0]);expected.append({'name':name,'private':private,'public':not private,'static':False,'declaring_class':'Swoole\\Server\\Port','has_default':True,'default':value,'type':{'null':'NULL','bool':'boolean','long':'integer'}[kind]})
 assert len(expected)==19
 report={'scope':__doc__,'pin':PIN,'expected':expected,'engines':[],'passed':False}
 for name,export in [('native',a.native),('selected',a.selected)]:
  meta=json.load(open(export/'export.json'));binary=export/'swoole.so';assert sha(binary)==meta['files']['swoole.so']['sha256'];command=[a.php,'-n','-d','extension='+str(binary.resolve()),str(Path(__file__).with_suffix('.php'))];r=run_isolated(command,timeout=30);row={'name':name,'export':str(export),'source_ref':meta['source_ref'],'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'passed':False};report['engines'].append(row)
  if r.returncode==0 and not r.stderr:
   row['observed']=json.loads(r.stdout);row['passed']=row['observed']['properties']==expected
  write_report(a.output,report)
  if not row['passed']:return 1
 assert report['engines'][0]['source_ref']==report['engines'][1]['source_ref']
 report['passed']=True;write_report(a.output,report);print('Both actual PHP engines match all19 Port declarations');return 0
if __name__=='__main__':sys.exit(main())
