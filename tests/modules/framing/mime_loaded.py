#!/usr/bin/env python3
"""Actual immutable native/selected PHP MIME APIs; catalog/suffix/mutation only, no server/network/parser/callback/stopped profile."""
from pathlib import Path
import argparse,json,subprocess,hashlib,re,sys
from collections import Counter
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--selected',type=Path,required=True);p.add_argument('--php',default='php');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('Refusing an existing receipt')
 raw=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':src/protocol/mime_type.cc'],text=True);entries=re.findall(r'\{"([^"\\]*)", "([^"\\]*)"\}',raw);assert len(entries)==362;catalog=dict(entries);assert len(catalog)==362
 def expected(filename):
  # Actual PHP facade passes ZSTR_VAL to C++ std::string: first NUL terminates.
  filename=filename.split('\0',1)[0];suffix=filename.rsplit('.',1)[-1].lower();return [filename,catalog.get(suffix,'application/octet-stream'),suffix in catalog]
 fixture={'catalog':[[k,catalog.get(k.lower(),'application/octet-stream'),k.lower()in catalog]for k in catalog], 'extra':[]}
 for filename in ['', 'txt', 'TXT', 'file.', '.html', 'a.b.JSON', 'directory.with.dot/no_suffix', 'file.unknown54','file.txt\0.html','file.unknown54\0.txt','a.b.c.svg']:
  _,value,present=expected(filename);fixture['extra'].append([filename,value,present])
 folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True);data=folder/'fixture.json';data.write_text(json.dumps(fixture)+'\n');report={'scope':__doc__,'pin':PIN,'catalog_entries':362,'engines':[],'passed':False,'whole_module_parity_passed':False,'performance_qualified':False,'server_or_network_parser_executed':False}
 wanted=[True,'application/x-first',True,False,'application/x-first',None,'application/x-second',None,'application/x-second',2,True,'application/x-second',True,False,False,'application/octet-stream',0]
 for name,export in [('native',a.native),('selected',a.selected)]:
  meta=json.load(open(export/'export.json'));binary=export/'swoole.so';assert sha(binary)==meta['files']['swoole.so']['sha256'];cmd=[a.php,'-n','-d','extension='+str(binary.resolve()),str(Path(__file__).with_suffix('.php')),str(data)];r=run_isolated(cmd,timeout=30);row={'name':name,'source_ref':meta['source_ref'],'export':str(export),'command':cmd,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'passed':False};report['engines'].append(row)
  if r.returncode==0 and not r.stderr:
   row['observed']=json.loads(r.stdout);o=row['observed'];row['passed']=Counter(o['catalog'])==Counter(catalog.values())and o['operations']==wanted and len(o['rows'])==735
  write_report(a.output,report)
  if not row['passed']:return 1
 first,last=[x['observed']for x in report['engines']];report['within_host_catalog_order_and_results_match']=all(first[k]==last[k]for k in ['catalog','rows','operations']);report['passed']=report['within_host_catalog_order_and_results_match'];assert report['engines'][0]['source_ref']==report['engines'][1]['source_ref'];write_report(a.output,report);print(json.dumps({'passed':report['passed'],'catalog':362,'lookups_per_engine':735,'mutation_observations_per_engine':17}));return int(not report['passed'])
if __name__=='__main__':sys.exit(main())
