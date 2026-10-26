#!/usr/bin/env python3
"""Actual async Client on/dispatch/free/connect bodies with native callback/effect doubles.

Typed parameter adapter is not real Zend parsing/refcount/bailout/native layout
or event-loop/lifetime proof. Invalid native dispatch enums abort and are excluded.
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
 scratch=out/'patched';scratch.mkdir(exist_ok=True);original='';destination='ext-src/swoole_client_async.cc'
 for path in gate.overlay_manifest()['upstream_paths']:
  text=gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']);dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
  if path==destination:original=text
 gate.apply_overlay(scratch,out);selected=(scratch/destination).read_text();native='';rust=''
 signatures=['void php_swoole_client_async_free_object(const ClientObject *client_obj) {','static sw_inline void client_execute_callback(zval *zobject, AsyncClientCallbackType type) {','static void client_onConnect(Client *cli) {','static PHP_METHOD(swoole_client_async, on) {','static PHP_METHOD(swoole_client_async, connect) {']
 for signature in signatures:
  before=gate.body(original,signature);after=gate.body(selected,signature)
  if before==after or 'swr_v1_clients_async_' not in after:raise ValueError('Missing actual async Rust caller')
  native+=before+'\n';rust+=after+'\n'
 unchanged=''
 for signature in ['static sw_inline void client_execute_callback_and_dtor(Client *cli, zval *zobject, AsyncClientCallbackType type) {','static void client_onClose(Client *cli) {','static void client_onError(Client *cli) {','static void client_onBufferFull(Client *cli) {','static void client_onBufferEmpty(Client *cli) {']:
  before=gate.body(original,signature)
  if before!=gate.body(selected,signature):raise ValueError('Unexpected change to native companion')
  unchanged+=before+'\n'
 enum=original[original.index('enum AsyncClientCallbackType {'):original.index('\n};',original.index('enum AsyncClientCallbackType {'))+3];helper=gate.body(selected,'static zend::Callable **clients_async_slot(const ClientObject *object, uint32_t slot) {')
 fixture=Path(__file__).with_name('async_witness.cpp');prelude,rest=fixture.read_text().split('// DECLARATIONS');facade=rest.split('// DRIVER')[0].replace('// PINNED_ENUM',enum);cpp=out/'actual_async.cpp'
 driver=gate.SHARDED_MAIN+r'''static int sharded_main(){try{throw std::runtime_error("initialize private fault injector");}catch(const std::exception&){}native::run(0,0,0,0,0);rust::run(0,0,0,0,0);size_t cases=0;auto compare=[&](unsigned bits,unsigned scenario,unsigned mutation,int failure,unsigned operation,const std::string&name="connect"){auto expected=native::run(bits,scenario,mutation,failure,operation,name),actual=rust::run(bits,scenario,mutation,failure,operation,name);if(expected!=actual){std::cerr<<bits<<":"<<scenario<<":"<<mutation<<":"<<operation<<":"<<failure<<"\n"<<expected<<"\n"<<actual<<"\n";return false;}++cases;return true;};
 if(SHARD_INDEX==0)for(unsigned base:{0u,127u,511u,65536u})for(const std::string&known:std::vector<std::string>{"connect","receive","close","error","bufferFull","bufferEmpty"})for(unsigned offset=0;offset<known.size()+2;++offset)for(unsigned byte=0;byte<256;++byte){std::string name=known+std::string("\0tail",5);name[offset]=static_cast<char>(byte);if(!compare(base,0,0,-1,0,name))return 1;}
 if(SHARD_INDEX==0)for(unsigned base:{0u,127u,511u,65536u})for(const std::string&name:std::vector<std::string>{"connect","receive","close","error","bufferFull","bufferEmpty"})for(size_t n=0;n<=name.size();++n)if(!compare(base,0,0,-1,0,name.substr(0,n)))return 1;
 if(SHARD_INDEX==0)for(unsigned extra:{0u,16384u,65536u,32768u,16384u|65536u,32768u|65536u,16384u|32768u,16384u|32768u|65536u})if(!compare(127u|extra,0,0,-1,4))return 1;
 if(SHARD_INDEX==0)for(unsigned flags:{127u,127u|4096u,127u|8192u,127u|8192u|4096u,2u|4096u,2u|4096u|8192u})for(unsigned mutation=0;mutation<13;++mutation)if(!compare(flags,1,mutation,-1,4))return 1;
 for(unsigned bits=SHARD_INDEX;bits<1024;bits+=SHARD_COUNT)for(unsigned scenario=0;scenario<6;++scenario)for(unsigned mutation=0;mutation<13;++mutation)for(unsigned operation=0;operation<5;++operation){unsigned flags=bits|((scenario&1)?(8192u|1024u):0u)|((scenario&2)?(4096u|2048u):0u)|((scenario&4)?32768u:0u);if(!compare(flags,scenario,mutation,-1,operation))return 1;if(bits%257==0)for(int failure=0;failure<24;++failure)if(!compare(flags,scenario,mutation,failure,operation))return 1;}std::cout<<cases<<"\n";return 0;}'''
 cpp.write_text(prelude+facade.replace('BODY_NAMESPACE','native').replace('// SLOT_HELPER','').replace('// ACTUAL_BODY',native+unchanged)+facade.replace('BODY_NAMESPACE','rust').replace('// SLOT_HELPER',helper).replace('// ACTUAL_BODY',rust+unchanged)+driver);exe=out/'actual_async';flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else [];gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe]);cases=gate.run_shards([exe])[0];report=dict(passed=True,native_case_locale='C process default; other locales unrun',cases=cases,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
