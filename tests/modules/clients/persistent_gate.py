#!/usr/bin/env python3
"""Actual PHP Client persistent acquisition/reuse/release branches with native effect doubles.

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
        if path=='ext-src/swoole_client.cc':original=text
    gate.apply_overlay(scratch,out);selected=(scratch/'ext-src/swoole_client.cc').read_text()
    native='';rust=''
    for signature in ['void php_swoole_client_free(const zval *zobject, Client *cli) {','static Client *php_swoole_client_new(zval *zobject, char *host, int host_len, int port) {']:
        before=gate.body(original,signature);after=gate.body(selected,signature)
        if before==after or 'swr_v1_clients_persistent_next' not in after:raise ValueError('No actual selected Rust persistent caller')
        native+=before+'\n';rust+=after+'\n'
    template=(Path(__file__).with_name('persistent_witness.cpp')).read_text()
    prelude,facade=template.split('// DECLARATIONS')
    facade=facade.split('// DRIVER')[0]
    cpp=out/'actual_persistent.cpp'
    driver=r'''int main(){size_t count=0;
      for(unsigned bits=0;bits<2048;bits++)for(unsigned scenario=0;scenario<9;scenario++)for(unsigned mode=0;mode<2;mode++){
        auto expected=native::run(bits,scenario,mode),actual=rust::run(bits,scenario,mode);
        if(expected!=actual){std::cerr<<"mismatch "<<bits<<":"<<scenario<<":"<<mode<<"\n"<<expected<<"\n"<<actual<<"\n";return 1;}++count;
      }std::cout<<count<<"\n";
    }'''
    cpp.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// ACTUAL_BODY',native)+'\n#define SWR_CLIENTS_WITNESS_RUST_POOL 1\n'+facade.replace('BODY_NAMESPACE','rust').replace('// ACTUAL_BODY',rust)+driver)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
    variants=[];cases=0
    for sockets in [False,True]:
        exe=out/('actual_persistent-sockets' if sockets else 'actual_persistent-no-sockets')
        defines=['-DSWOOLE_SOCKETS_SUPPORT=1'] if sockets else []
        gate.run(['c++','-std=c++17','-O1',*defines,*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe])
        count=int(gate.run([exe]).strip());cases+=count;variants.append(dict(sockets_support=sockets,cases=count))
    report=dict(passed=True,cases=cases,variants=variants,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
