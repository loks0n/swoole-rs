#!/usr/bin/env python3
"""Actual Address numeric parse/assign/loopback bodies against platform inet_pton.

Native sockaddr layouts and platform libc are real; resolver is a deterministic effect adapter, not DNS/runtime proof.
OS unsupported-family errno and native address publication/resolver effects stay outside Rust.
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
 scratch=out/'patched';scratch.mkdir(exist_ok=True);original='';destination='src/network/address.cc'
 for path in gate.overlay_manifest()['upstream_paths']:
  text=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']);dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
  if path==destination:original=text
 gate.apply_overlay(scratch,out);selected=(scratch/destination).read_text();signatures=['bool Address::verify_ip(int family, const std::string &str) {','bool Address::verify_port(const int port, const bool for_connect) {','bool Address::assign(SocketType _type, const std::string &_host, int _port, bool _resolve_name) {','bool Address::is_loopback_addr() const {'];before='';after=''
 for signature in signatures:
  native=gate.body(original,signature);rust=gate.body(selected,signature)
  if native==rust:raise ValueError('Missing actual address caller')
  before+=native+'\n';after+=rust+'\n'
 before=gate.body(original,'static bool IN_IS_ADDR_LOOPBACK(const in_addr *a) {')+'\n'+before
 after=gate.body(selected,'static int clients_parse_ip(int family, const std::string &host, void *destination) {')+'\n'+after

 fixture=Path(__file__).with_name('ip_witness.cpp');prelude,rest=fixture.read_text().split('// DECLARATIONS');facade=rest.split('// DRIVER')[0];cpp=out/'actual_ip.cpp'
 driver=r'''int main(){std::vector<std::string>inputs={"","0.0.0.0","127.0.0.1","127.1.2.3","255.255.255.255","01.2.3.4","08.009.000.001","::ffff:01.02.03.004","1.2.3.256","1.2.3","+1.2.3.4","1.2.3.4 ","::","::1","::ffff:192.0.2.1","::192.0.2.1","2001:db8::1","1:2:3:4:5:6:7:8","::%lo0","::%","::1%tail","fe80::1%99999999999999999","1.2.3.4%scope","::1%scope:foo","::1%\xff","resolve-fail","localhost",std::string("127.0.0.1\0tail",14),std::string("::1\0tail",8)};for(const auto&seed:std::vector<std::string>{"127.0.0.1","2001:db8::1","::ffff:192.0.2.1"})for(size_t pos=0;pos<seed.size();++pos)for(unsigned byte=0;byte<256;++byte){auto item=seed;item[pos]=static_cast<char>(byte);inputs.push_back(item);}for(unsigned n=0;n<2048;++n){inputs.push_back(std::to_string(n%256)+"."+std::to_string((n/2)%256)+"."+std::to_string((n/3)%256)+"."+std::to_string((n/5)%256));std::ostringstream ipv6;ipv6<<std::hex<<n<<":"<<(n*31)<<"::"<<(n*59);inputs.push_back(ipv6.str());}for(unsigned zeroes=0;zeroes<64;++zeroes){inputs.push_back(std::string(zeroes,'0')+"1.2.3.4");inputs.push_back("::ffff:"+std::string(zeroes,'0')+"1.2.3.4");}for(size_t length:{103,104,105,106,107,108,109,110})inputs.push_back(std::string(length,'x'));size_t cases=0;for(size_t i=0;i<inputs.size();++i){const auto&host=inputs[i];for(int family:{AF_INET,AF_INET6,AF_UNIX,-1}){auto expected=native::verify(family,host),actual=rust::verify(family,host);if(expected!=actual){std::cerr<<"verify:"<<i<<":"<<family<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++cases;}if(i<1024||i>=inputs.size()-8)for(int type:{0,1,2,3,4,5,6,7})for(int port:{-1,0,1,65535,65536})for(bool resolve:{false,true}){auto expected=native::assign(type,host,port,resolve),actual=rust::assign(type,host,port,resolve);if(expected!=actual){std::cerr<<"assign:"<<i<<":"<<type<<":"<<port<<":"<<resolve<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++cases;}}std::vector<uint8_t>bytes(16);for(unsigned n=0;n<65536;++n){for(unsigned i=0;i<16;++i)bytes[i]=(n>>(i%2*8))&255;for(int type:{0,1,2,3,4,5,6,7}){if(native::loopback(type,bytes)!=rust::loopback(type,bytes))return 1;++cases;}}for(unsigned i=0;i<16;++i){bytes.assign(16,0);bytes[i]=1;for(int type:{0,1,2,3,4,5,6,7}){if(native::loopback(type,bytes)!=rust::loopback(type,bytes))return 1;++cases;}}std::cout<<cases<<"\n";}'''


 cpp.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// ACTUAL_BODY',before)+facade.replace('BODY_NAMESPACE','rust').replace('// ACTUAL_BODY',after)+driver);exe=out/'actual_ip';flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
 gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe]);cases=int(gate.run([exe]).strip())
 report=dict(passed=True,cases=cases,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
