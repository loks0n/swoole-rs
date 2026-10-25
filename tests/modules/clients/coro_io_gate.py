#!/usr/bin/env python3
"""Actual coroutine Client datagram/peek/connected/endpoint/close binding bodies.

Parameter macros use a typed test adapter; no actual Zend parsing, coroutine, IO or Socket custody claim.
Native Socket/strings/reference outputs/allocator effects stay outside Rust.
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
 scratch=out/'patched';scratch.mkdir(exist_ok=True);original='';destination='ext-src/swoole_client_coro.cc'
 for path in gate.overlay_manifest()['upstream_paths']:
  text=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']);dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
  if path==destination:original=text
 gate.apply_overlay(scratch,out);selected=(scratch/destination).read_text();signatures=['static sw_inline SocketImpl *client_coro_get_socket_for_connect(zval *zobject, int port) {',*[f'static PHP_METHOD(swoole_client_coro, {name}) {{' for name in ['sendto','recvfrom','peek','isConnected','getsockname','getpeername','close']]];before='';after=''
 for signature in signatures:
  native=gate.body(original,signature);rust=gate.body(selected,signature)
  if native==rust or 'swr_v1_clients_coro_next' not in rust:raise ValueError('Missing actual coroutine binding caller')
  before+=native+'\n';after+=rust+'\n'

 after=after.replace('static PHP_METHOD(swoole_client_coro, sendto) {',gate.body(selected,'static SocketImpl *clients_coro_datagram_socket(zval *zobject) {')+'\nstatic PHP_METHOD(swoole_client_coro, sendto) {',1)
 fixture=Path(__file__).with_name('coro_io_witness.cpp');prelude,rest=fixture.read_text().split('// DECLARATIONS');facade=rest.split('// DRIVER')[0];cpp=out/'actual_coro_io.cpp'
 driver=r'''int main(){size_t cases=0;for(unsigned bits=0;bits<2048;++bits)for(unsigned scenario=0;scenario<7;++scenario)for(unsigned mutation=0;mutation<20;++mutation)for(unsigned operation=0;operation<7;++operation){auto compare=[&](int failure){auto expected=native::run(bits,scenario,mutation,failure,operation),actual=rust::run(bits,scenario,mutation,failure,operation);if(expected!=actual){std::cerr<<bits<<":"<<scenario<<":"<<mutation<<":"<<operation<<":"<<failure<<"\n"<<expected<<"\n"<<actual<<"\n";return false;}++cases;return true;};if(!compare(-1))return 1;if(bits%257==0)for(int failure=0;failure<24;++failure)if(!compare(failure))return 1;}std::cout<<cases<<"\n";}'''

 cpp.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// ACTUAL_BODY',before)+facade.replace('BODY_NAMESPACE','rust').replace('// ACTUAL_BODY',after)+driver);exe=out/'actual_coro_io';flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
 gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe]);cases=int(gate.run([exe]).strip())
 report=dict(passed=True,cases=cases,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
