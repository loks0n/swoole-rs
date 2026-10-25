#!/usr/bin/env python3
"""Actual resolver configuration/endpoint bodies with real private FILE IO.

Native integer conversion/locale/errno are preserved. This is not live resolver,
c-ares, whole PHP runtime or global storage lifetime parity.
"""
import argparse
import json
from pathlib import Path
import gate

ROOT=Path(__file__).resolve().parents[3]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--archive',type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--sanitize',action='store_true')
    p.add_argument('--rust-sanitized',action='store_true')
    a=p.parse_args();out=a.output.parent/(a.output.stem+'-artifacts');out.mkdir(parents=True,exist_ok=True);gate.LOG=out/'commands';gate.LOG.mkdir(exist_ok=True)
    if a.rust_sanitized and not (a.sanitize and a.archive):p.error('--rust-sanitized needs --archive and --sanitize')
    archive=a.archive or out/'libclients.a'
    if not a.archive:gate.run(['rustc','--edition','2024','--crate-type','staticlib','-O','-C','panic=abort',ROOT/'crates/clients/src/lib.rs','-o',archive])
    scratch=out/'patched';scratch.mkdir(exist_ok=True);original=''
    for path in gate.overlay_manifest()['upstream_paths']:
        text=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']);dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
        if path=='src/network/dns.cc':original=text
    gate.apply_overlay(scratch,out);selected=(scratch/'src/network/dns.cc').read_text()
    native='';rust=''
    for signature in ['SW_API void swoole_set_dns_server(const std::string &server) {','SW_API bool swoole_load_resolv_conf() {']:
        before=gate.body(original,signature);after=gate.body(selected,signature)
        if before==after or 'swr_v1_clients_' not in after:raise ValueError('No actual selected Rust resolver configuration caller')
        native+=before+'\n';rust+=after+'\n'
    address_native=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:src/network/address.cc'])
    address_selected=(scratch/'src/network/address.cc').read_text()
    native_port=gate.body(address_native,'bool Address::verify_port(const int port, const bool for_connect) {')
    selected_port=gate.body(address_selected,'bool Address::verify_port(const int port, const bool for_connect) {')
    header=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:include/swoole.h'])
    integers=gate.body(header,'static inline long sw_atol(const char *str) {')+'\n'+gate.body(header,'static inline int sw_atoi(const char *str) {')
    template=(Path(__file__).with_name('resolv_witness.cpp')).read_text()
    prelude,facade=template.replace('// NATIVE_INTEGER',integers).split('// DECLARATIONS')
    facade=facade.split('// DRIVER')[0]
    cpp=out/'actual_resolv.cpp'
    driver=r'''int main(int argc,char **argv){if(argc!=2)return 9;size_t count=0;
      for(const std::string&host:std::vector<std::string>{"","a","127.0.0.1"," "})for(int port=-3;port<=65538;port++){
        const auto value=host+":"+std::to_string(port);auto expected=native::endpoint(value),actual=rust::endpoint(value);
        if(expected!=actual){std::cerr<<"endpoint "<<value<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++count;
      }
      std::vector<std::string> values={"","127.0.0.1","a:",":53","::1","a:+53","a:-1","a: 54junk","a:0x35","a:9999999999999999999999999",std::string("a\0b:54",6),std::string("a:54\0:99",8)};
      for(unsigned byte=1;byte<256;byte++){values.push_back("a:"+std::string(1,char(byte))+"53");values.push_back(std::string(1,char(byte))+":53");}
      for(const auto&value:values){auto expected=native::endpoint(value),actual=rust::endpoint(value);if(expected!=actual){std::cerr<<"endpoint bytes mismatch\n";return 2;}++count;}
      const std::vector<std::string> lines={"","#ignored\n","nameserver 127.0.0.1\n"," nameserver 1.1.1.1\n","nameserver  1.1.1.1\n","nameserver 1.1.1.1\r\n","nameserverX 1.1.1.1\n","nameserver  \n","nameserver 1.1.1.1:54\n","nameserver 1.1.1.1 \n",std::string("nameserver 1.1\0extra\n",sizeof("nameserver 1.1\0extra\n")-1)};
      for(const auto&first:lines)for(const auto&second:lines){auto text=first+second;auto expected=native::config(text,argv[1],true),actual=rust::config(text,argv[1],true);if(expected!=actual){std::cerr<<"config mismatch\n"<<expected<<"\n"<<actual<<"\n";return 3;}++count;}
      for(const auto&text:std::vector<std::string>{std::string(99,'z')+"nameserver 1.1.1.1\n",std::string(120,'z')+"\nnameserver 1.1.1.1\n"}){if(native::config(text,argv[1],true)!=rust::config(text,argv[1],true))return 6;++count;}
      auto expected=native::config("",argv[1],false),actual=rust::config("",argv[1],false);if(expected!=actual)return 4;++count;
      for(const std::string&line:std::vector<std::string>{"nameserver","nameserver \n","nameserver\t1.1.1.1\n","nameservertoolong 1.1.1.1\n","nameserver 1234567890123456\n"}){
        auto plan=swr_v1_clients_resolv_line(reinterpret_cast<const uint8_t*>(line.data()),line.size());if(plan.kind!=2)return 5;
      }
      std::cout<<count<<"\n";
    }'''
    cpp.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// ACTUAL_PORT',native_port).replace('// ACTUAL_BODY',native)+facade.replace('BODY_NAMESPACE','rust').replace('// ACTUAL_PORT',selected_port).replace('// ACTUAL_BODY',rust)+driver)
    exe=out/'actual_resolv';flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
    gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe]);cases=int(gate.run([exe,out/'private-resolv.conf']).strip())
    report=dict(passed=True,cases=cases,scope=__doc__,pin=gate.PIN,excluded_native_undefined=['Original32-byte endpoint copy overflow and16-byte config token copy overflow/null strtok are excluded. Rust bounds failures are defensive outcomes, never native parity cases.'],native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
