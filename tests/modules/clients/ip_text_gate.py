#!/usr/bin/env python3
"""Actual pinned/selected DNS address text formatter with native string return.

Exact bytes/errno/input retention; no allocation-failure topology, resolver,
coherent extension, runtime or performance qualification.
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
 scratch=out/'patched';scratch.mkdir(exist_ok=True);original='';destination='src/network/dns.cc'
 for path in gate.overlay_manifest()['upstream_paths']:
  text=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']);dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
  if path==destination:original=text
 gate.apply_overlay(scratch,out);selected=(scratch/destination).read_text();signature='static std::string parse_ip_address(void *vaddr, int type) {';before=gate.body(original,signature);after=gate.body(selected,signature)
 if before==after or 'swr_v1_clients_ip_text' not in after:raise ValueError('Missing actual DNS text caller')
 base=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:src/core/base.cc']);printf=gate.body(base,'size_t sw_snprintf(char *buf, size_t size, const char *format, ...) {')
 prelude=r'''
#include "swoole_rs_clients.h"
#include <arpa/inet.h>
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#define sw_unlikely(x) (x)
'''
 driver=r'''int main(){size_t cases=0;std::array<uint8_t,32>bytes;auto compare=[&](){for(int family:{AF_INET,AF_INET6}){auto saved=bytes;errno=17;auto expected=native::parse_ip_address(bytes.data(),family);int error=errno;if(bytes!=saved)return false;errno=17;auto actual=rust::parse_ip_address(bytes.data(),family);if(expected!=actual||error!=errno||bytes!=saved){std::cerr<<family<<":"<<expected<<":"<<actual<<":"<<error<<":"<<errno<<"\n";return false;}++cases;}return true;};for(unsigned n=0;n<65536;++n){for(unsigned i=0;i<bytes.size();++i)bytes[i]=(n>>(i%2*8))&255;if(!compare())return 1;}for(unsigned pos=0;pos<16;++pos)for(unsigned n=0;n<256;++n){bytes.fill(0);bytes[pos]=n;if(!compare())return 1;bytes.fill(255);bytes[pos]=n;if(!compare())return 1;}uint32_t random=1234567;for(unsigned n=0;n<65536;++n){for(auto&byte:bytes){random=random*1664525+1013904223;byte=random>>24;}if(!compare())return 1;}std::cout<<cases<<"\n";}'''
 cpp=out/'actual_ip_text.cpp';cpp.write_text(prelude+'namespace native {\n'+printf+'\n'+before+'\n}\nnamespace rust {\n'+after+'\n}\n'+driver);exe=out/'actual_ip_text';flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
 gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe]);cases=int(gate.run([exe]).strip())
 report=dict(passed=True,cases=cases,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
