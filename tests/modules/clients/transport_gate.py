#!/usr/bin/env python3
"""Actual UDP/Unix/DTLS connect and async TCP backpressure branches with native effect doubles.

Public class layout, real Socket custody, reactor/PHP runtime and crypto lifetime
remain separate gates. No OS descriptors/files or user callbacks are invoked.
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
        if path=='src/network/client.cc':original=text
    gate.apply_overlay(scratch,out);selected=(scratch/'src/network/client.cc').read_text()
    native='';rust=''
    for signature in ['static int Client_udp_connect(Client *cli, const char *host, int port, double timeout, int udp_connect) {','static ssize_t Client_tcp_send_async(Client *cli, const char *data, size_t length, int flags) {','static ssize_t Client_udp_send(Client *cli, const char *data, size_t len, int flags) {']:
        before=gate.body(original,signature);after=gate.body(selected,signature)
        if before==after or 'swr_v1_clients_' not in after:raise ValueError('No actual selected Rust transport caller')
        native+=before+'\n';rust+=after+'\n'
    template=(Path(__file__).with_name('transport_witness.cpp')).read_text()
    prelude,facade=template.split('// DECLARATIONS')
    facade=facade.split('// DRIVER')[0]
    cpp=out/'actual_transport.cpp'
    driver=r'''int main(){size_t count=0;
      for(unsigned bits=0;bits<1024;bits++)for(unsigned scenario=0;scenario<10;scenario++)for(unsigned outcome=0;outcome<6;outcome++)for(unsigned mode=0;mode<2;mode++)for(int udp_connect=0;udp_connect<(mode==0?3:1);udp_connect++){
        auto expected=native::run(bits,scenario,outcome,mode,udp_connect),actual=rust::run(bits,scenario,outcome,mode,udp_connect);
        if(expected!=actual){std::cerr<<"mismatch "<<bits<<":"<<scenario<<":"<<outcome<<":"<<mode<<":"<<udp_connect<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++count;
      }
      for(ssize_t result:std::vector<ssize_t>{-3,-1,0,1,2,5,SSIZE_MAX})for(size_t length:std::vector<size_t>{0,1,2,5,6,size_t(SSIZE_MAX),size_t(SSIZE_MAX)+1,SIZE_MAX}){
        if(native::datagram(result,length)!=rust::datagram(result,length))return 2;++count;
      }
      std::cout<<count<<"\n";
    }'''
    cpp.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// ACTUAL_BODY',native)+facade.replace('BODY_NAMESPACE','rust').replace('// ACTUAL_BODY',rust)+driver)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
    variants=[];cases=0
    for dtls in [False,True]:
        exe=out/('actual_transport-dtls' if dtls else 'actual_transport-no-dtls')
        defines=['-DSW_SUPPORT_DTLS=1'] if dtls else []
        gate.run(['c++','-std=c++17','-O1',*defines,*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe])
        count=int(gate.run([exe]).strip());cases+=count;variants.append(dict(dtls_support=dtls,cases=count))
    report=dict(passed=True,cases=cases,variants=variants,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
