#!/usr/bin/env python3
"""Actual HTTP receive/parser/result bodies with native Socket/parser/Zend effect doubles.

No actual IO/parser/Zend bailout or whole socket lifetime claim.
Only initialized bounded receive backing is compared.
"""
import argparse,json
from pathlib import Path
import gate
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-sanitized',action='store_true');a=p.parse_args()
 if a.rust_sanitized and not(a.archive and a.sanitize):p.error('--rust-sanitized requires --archive and --sanitize')
 out=a.output.parent/(a.output.stem+'-artifacts');out.mkdir(parents=True,exist_ok=True);gate.LOG=out/'commands';gate.LOG.mkdir(exist_ok=True);archive=a.archive or out/'libclients.a'
 if not a.archive:gate.run(['rustc','--edition','2024','--crate-type','staticlib','-O','-C','panic=abort',ROOT/'crates/clients/src/lib.rs','-o',archive])
 scratch=out/'patched';scratch.mkdir(exist_ok=True);original='';destination='ext-src/swoole_http_client_coro.cc'
 for path in gate.overlay_manifest()['upstream_paths']:
  text=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']);dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
  if path==destination:original=text
 gate.apply_overlay(scratch,out);selected=(scratch/destination).read_text();signature='bool Client::recv_response(double timeout) {';before=gate.body(original,signature);after=gate.body(selected,signature)
 if before==after or 'swr_v1_clients_http_response_next' not in after:raise ValueError('Missing real resolver caller')
 fixture=Path(__file__).with_name('http_response_witness.cpp');prelude,rest=fixture.read_text().split('// DECLARATIONS');facade=rest.split('// DRIVER')[0];cpp=out/'actual_http_response.cpp'
 driver=r'''int main(){size_t cases=0;for(unsigned bits=0;bits<32768;++bits)for(unsigned scenario=0;scenario<8;++scenario)for(unsigned mutation=0;mutation<10;++mutation){auto expected=native::run(bits,scenario,mutation,-1),actual=rust::run(bits,scenario,mutation,-1);if(expected!=actual){std::cerr<<bits<<":"<<scenario<<":"<<mutation<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++cases;if(bits%257==0)for(int failure=0;failure<24;++failure){expected=native::run(bits,scenario,mutation,failure);actual=rust::run(bits,scenario,mutation,failure);if(expected!=actual){std::cerr<<bits<<":"<<scenario<<":"<<mutation<<":"<<failure<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++cases;}}std::cout<<cases<<"\n";}'''

 cpp.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// ACTUAL_BODY',before)+facade.replace('BODY_NAMESPACE','rust').replace('// ACTUAL_BODY',after)+driver);exe=out/'actual_http_response';flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
 gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe]);cases=int(gate.run([exe]).strip())
 report=dict(passed=True,cases=cases,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
