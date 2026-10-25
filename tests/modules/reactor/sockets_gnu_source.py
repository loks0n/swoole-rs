#!/usr/bin/env python3
"""Compare GNU candidate Rust policy with exact official C++ source bodies.
Host-only inert metadata facades; never installed-image/Native Linux parity.
"""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys
import uuid
from gnu_source_body import render

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.dev_cache import compile_cached


def traces():
    result=[]
    for offset,stride in [(0,n) for n in [1,13,29,59,127,169,-13,-29]]+[(-2147483648,13),(2147483647,-13)]:
        keys=[offset+i*stride for i in range(65)]
        result.append('n')
        for i,key in enumerate(keys):
            result.append(f'p {key} {i+100}')
            if i%7==0:result.append(f'p {key} {i+900}')
        for key in keys[::3]:result.append(f'e {key}')
        for key in keys[::3]:result.append(f'g {key}')
        result.append('c')
        for key in keys[::7]:result.append(f'p {key} 1')
    return '\n'.join(result)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-dir',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    if a.report.exists():p.error('Choose a unique report')
    work=a.report.parent/('gnu-source-body-'+uuid.uuid4().hex);work.mkdir(parents=True)
    r=dict(passed=False,scope=__doc__,assigned_to='@loks0n',work=str(work.resolve()),commands=[],native_linux_qualified=False,image_provenance_attested=False,activation=False,allocation_effects_modeled=False)
    def run(command,*,input_text=None,output=None):
        require_build_space(work)
        row=compile_cached(command,output=output,scratch=work) if output else None
        if row is None:
            result=subprocess.run(list(map(str,command)),input=input_text,text=True,capture_output=True,timeout=60)
            row=dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        r['commands'].append(dict(command=list(map(str,command)),**row));a.report.write_text(json.dumps(r,indent=2)+'\n')
        if row['returncode'] or row['stderr']:raise ValueError('Source-body command failed/warned')
        return row['stdout']
    try:
        text,proof=render(a.candidate_dir);(work/'actual-gnu.inc').write_text(text);r['official_source_binding']=proof
        trace=traces();(work/'trace.txt').write_text(trace);r['scenarios']=10;r['states']=len(trace.splitlines())
        expected=None
        fixture=Path(__file__).with_suffix('.cc').resolve()
        for standard,opt,sanitize in [('c++14','0',False),('c++14','2',False),('c++17','0',False),('c++17','2',False),('c++14','1',True)]:
            binary=work/(standard+'-O'+opt+('-asan' if sanitize else ''))
            command=['c++','-std='+standard,'-O'+opt,'-I'+str(work.resolve()),fixture,'-o',binary]
            if sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            run(command,output=binary);observed=run([binary],input_text=trace)
            if expected is None:expected=observed;(work/'expected.tsv').write_text(expected)
            elif observed!=expected:raise ValueError('Host source-body profiles disagree')
            binary.unlink()
        r['source_body_profiles']=5
        # Compile the exact current Rust module with one test-only adapter; no new
        # production C export or policy activation is introduced.
        rust=ROOT/'crates/reactor/src/sockets.rs'
        table=rust.read_text().split('const PRIMES: &[u64] = &[',1)[1].split('];',1)[0]
        if [int(value) for value in re.findall(r'\d+',table)]!=proof['prime_values_u64']:
            raise ValueError('Rust bucket data differs from all304 official source values')
        r['prime_values_verified']=len(proof['prime_values_u64'])
        adapter=r'''
#[test]
fn gnu_official_source_body_ordinary_metadata() {
    let mut owner=ReactorSocketStore::<true>::new();
    fn values(entries:&[ReactorSocketEntry])->String {
        if entries.is_empty(){return "-".to_owned();}
        entries.iter().map(|entry|format!("{}:{};",entry.fd,entry.token)).collect()
    }
    for (step,line) in include_str!("expected.tsv").lines().enumerate() {
        let fields:Vec<_>=line.split('\t').collect();assert_eq!(fields.len(),8);
        let key:i32=fields[1].parse().unwrap();let token:usize=fields[2].parse().unwrap();
        match fields[0] {
            "n"=>owner=ReactorSocketStore::<true>::new(),
            "p"=>owner.put(key,token).unwrap(),
            "g"=>{if owner.find(key).is_none(){owner.put(key,0).unwrap();}},
            "e"=>owner.erase(key),
            "c"=>{let keys:Vec<_>=owner.snapshot_entries().unwrap().iter().map(|entry|entry.fd).collect();for key in keys{owner.erase(key);}},
            _=>panic!("Unknown source trace"),
        }
        assert_eq!(owner.len(),fields[3].parse::<usize>().unwrap(),"count step{step}");
        assert_eq!(owner.buckets.len().max(1),fields[4].parse::<usize>().unwrap(),"buckets step{step}");
        let threshold=if owner.buckets.is_empty(){0}else{gnu_resize_threshold(owner.buckets.len())};
        assert_eq!(threshold,fields[5].parse::<usize>().unwrap(),"threshold step{step}");
        let actual=values(&owner.snapshot_entries().unwrap());
        assert_eq!(actual,fields[6],"live step{step}");
        assert_eq!(actual,fields[7],"copy step{step}");
    }
}
'''
        owner=ROOT/'crates/reactor/src/owner.rs'
        (work/'owner.rs').write_bytes(owner.read_bytes())
        (work/'source-test.rs').write_text(rust.read_text()+'\nmod owner;\n'+adapter)
        binary=work/'source-test';run(['rustc','--edition=2024','--test',work/'source-test.rs','-o',binary]);run([binary,'--nocapture'])
        r.update(passed=True,source_body_states_compared=r['states'],state_comparisons_per_state=5,rust_tests=5,limits=['Official header/release bodies executed through explicit inert host metadata helpers, not actual GCC/libstdc++ or installed Linux code.','Allocation retention, exceptions, deallocation/lifetime/resource traces and Native target ABI/codegen are outside this oracle.','Signed keys are ordinary values; no invalid storage, Native faults, runtime, callbacks, network, timing or stopped profile.','Current Apple controls and actual producer qualifications remain separately source-bound; Linux ON stays refused.'])
    except Exception as error:r['error']=str(error)
    a.report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k) for k in ['passed','error','states','native_linux_qualified']}));return int(not r['passed'])

if __name__=='__main__':raise SystemExit(main())
