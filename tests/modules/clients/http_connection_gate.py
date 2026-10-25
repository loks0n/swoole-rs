#!/usr/bin/env python3
"""Actual HTTP Client connect/liveness/close bodies with native Socket/Zend effect doubles.

No actual coroutine socket, Zend bailout, crypto or full lifetime/runtime proof.
"""
import argparse,json
from pathlib import Path
import gate
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--archive',type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-sanitized',action='store_true');p.add_argument('--quick',action='store_true',help='Factorized local feedback; canonical default exhaustive corpus unchanged');a=p.parse_args()
 if a.rust_sanitized and not(a.archive and a.sanitize):p.error('--rust-sanitized requires --archive and --sanitize')
 out=a.output.parent/(a.output.stem+'-artifacts');out.mkdir(parents=True,exist_ok=True);gate.LOG=out/'commands';gate.LOG.mkdir(exist_ok=True);archive=a.archive or out/'libclients.a'
 if not a.archive:gate.run(['rustc','--edition','2024','--crate-type','staticlib','-O','-C','panic=abort',ROOT/'crates/clients/src/lib.rs','-o',archive])
 scratch=out/'patched';scratch.mkdir(exist_ok=True);original='';destination='ext-src/swoole_http_client_coro.cc'
 for path in gate.overlay_manifest()['upstream_paths']:
  text=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']);dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
  if path==destination:original=text
 gate.apply_overlay(scratch,out);selected=(scratch/destination).read_text();native='';rust=''
 for signature in ['bool Client::connect() {','bool Client::keep_liveness() {','bool Client::close(const bool should_be_reset) {']:
  before=gate.body(original,signature);after=gate.body(selected,signature)
  if before==after or 'swr_v1_clients_http_connection_next' not in after:raise ValueError('Missing real HTTP connection caller')
  native+=before+'\n';rust+=after+'\n'
 fixture=Path(__file__).with_name('http_connection_witness.cpp');prelude,rest=fixture.read_text().split('// DECLARATIONS');facade=rest.split('// DRIVER')[0];cpp=out/'actual_http_connection'
 driver=r'''int main(){size_t cases=0;for(unsigned bits=0;bits<16384;++bits)for(unsigned operation=0;operation<3;++operation)for(unsigned mutation=0;mutation<14;++mutation)for(int failure:{-1,0,4,8,12,16}){auto expected=native::run(bits,mutation,failure,operation),actual=rust::run(bits,mutation,failure,operation);if(expected!=actual){std::cerr<<bits<<":"<<operation<<":"<<mutation<<":"<<failure<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++cases;}std::cout<<cases<<"\n";}'''
 if a.quick:
  driver=r'''int main(){size_t cases=0;for(unsigned bits=0;bits<16384;++bits)for(unsigned operation=0;operation<3;++operation)for(unsigned mutation=0;mutation<14;++mutation){auto compare=[&](int failure){auto expected=native::run(bits,mutation,failure,operation),actual=rust::run(bits,mutation,failure,operation);if(expected!=actual){std::cerr<<bits<<":"<<operation<<":"<<mutation<<":"<<failure<<"\n"<<expected<<"\n"<<actual<<"\n";return false;}++cases;return true;};if(!compare(-1))return 1;if(bits%257==0)for(int failure=0;failure<25;++failure)if(!compare(failure))return 1;}std::cout<<cases<<"\n";}'''

 source=cpp.with_suffix('.cpp');source.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// ACTUAL_BODY',native)+facade.replace('BODY_NAMESPACE','rust').replace('// ACTUAL_BODY',rust)+driver);flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else [];variants=[]
 for zlib in [False,True]:
  exe=Path(str(cpp)+('-zlib' if zlib else '-no-zlib'));defines=['-DSW_HAVE_ZLIB=1'] if zlib else [];gate.run(['c++','-std=c++17','-O1',*defines,*flags,'-I',ROOT/'native/clients',source,archive,'-lpthread','-ldl','-lm','-o',exe]);variants.append(dict(zlib=zlib,cases=int(gate.run([exe]).strip())))
 report=dict(passed=True,coverage_profile='factorized-local' if a.quick else 'exhaustive-canonical',cases=sum(x['cases'] for x in variants),variants=variants,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
