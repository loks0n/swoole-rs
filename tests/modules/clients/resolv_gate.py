#!/usr/bin/env python3
"""Actual resolver configuration/endpoint bodies with real private FILE IO.

Native integer conversion/locale/errno are preserved. This is not live resolver,
c-ares, whole PHP runtime or global storage lifetime parity.
"""
import argparse
import json
from pathlib import Path
import sys
import gate

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import hybrid_tree

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--archive',required=True,type=Path,help='Rust archive of the hybrid build under test')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--sanitize',action='store_true')
    p.add_argument('--rust-sanitized',action='store_true')
    a=p.parse_args();out=a.output.parent/(a.output.stem+'-artifacts');out.mkdir(parents=True,exist_ok=True);gate.LOG=out/'commands';gate.LOG.mkdir(exist_ok=True)
    if a.rust_sanitized and not a.sanitize:p.error('--rust-sanitized needs --sanitize')
    # Native side from the pin, Rust side from the hybrid build's fully patched tree.
    hybrid_source,hybrid_flags=hybrid_tree(a.archive)
    trees={'native':lambda path:gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']),'rust':lambda path:(hybrid_source/path).read_text()}
    original=trees['native']('src/network/dns.cc');selected=trees['rust']('src/network/dns.cc')
    bodies={'native':'','rust':''}
    for signature in ['SW_API void swoole_set_dns_server(const std::string &server) {','SW_API bool swoole_load_resolv_conf() {']:
        before=gate.body(original,signature);after=gate.body(selected,signature)
        if before==after or 'swr_v1_clients_' not in after:raise ValueError('No actual selected Rust resolver configuration caller')
        bodies['native']+=before+'\n';bodies['rust']+=after+'\n'
    template=(Path(__file__).with_name('resolv_witness.cpp')).read_text()
    prelude,facade=template.split('// DECLARATIONS');facade,rest=facade.split('// ENTRY');entry=rest.split('// DRIVER')[0]
    def side(name):
        read=trees[name];header=read('include/swoole.h')
        integers=gate.body(header,'static inline long sw_atol(const char *str) {')+'\n'+gate.body(header,'static inline int sw_atoi(const char *str) {')
        port=gate.body(read('src/network/address.cc'),'bool Address::verify_port(const int port, const bool for_connect) {')
        return ('#include "swoole_rs_clients.h"\n' if name=='rust' else '')+prelude.replace('// NATIVE_INTEGER',integers)+facade.replace('BODY_NAMESPACE',name).replace('// ACTUAL_PORT',port).replace('// ACTUAL_BODY',bodies[name])
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
    # Each side in its own translation unit: the native one sees only pinned text.
    native,rust=out/'native_resolv.cpp',out/'actual_resolv.cpp'
    native.write_text(side('native'));rust.write_text(side('rust')+entry+driver)
    exe=out/'actual_resolv';flags=['-std=c++17','-O1',*(['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else [])]
    gate.run(['c++',*flags,'-c',native,'-o',out/'native_resolv.o'])
    gate.run(['c++',*flags,*hybrid_flags,rust,out/'native_resolv.o',a.archive,'-lpthread','-ldl','-lm','-o',exe]);cases=int(gate.run([exe,out/'private-resolv.conf']).strip())
    report=dict(passed=True,cases=cases,scope=__doc__,pin=gate.PIN,hybrid_tree=str(hybrid_source),not_compared=['Endpoints and config tokens beyond their fixed sizes are outside the compared domain; Rust stops at bounds there.'],native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
