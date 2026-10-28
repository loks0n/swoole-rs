#!/usr/bin/env python3
"""Actual Client::close bodies with native effect/deletion/reentry doubles.

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
    signature='int Client::close() {';native=gate.body(original,signature);rust=gate.body(selected,signature)
    if native==rust or 'swr_v1_clients_close(' not in rust:raise ValueError('No actual selected Rust lifecycle caller')
    prelude=r'''
#include <cstdint>
#include <string>
#include <vector>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <exception>
#include <memory>
#include <iostream>
#include "swoole_rs_clients.h"
#define SW_ERR -1
#define SW_OK 0
#define SW_TRACE_CLIENT 0
#define SW_SOCK_UNIX_DGRAM 5
static std::vector<std::string> effects;
static std::function<std::string()> probe;
static std::function<void()> ssl_hook,event_hook,timer_hook;
static int close_result=0;
static void observe(const std::string&event){effects.push_back(event+":"+(probe?probe():""));}
#define swoole_trace_log(...) ((void)0)
struct TimerNode {int id=0;};
struct Socket {
    void *object=nullptr,*ssl=nullptr;int fd=123,socket_type=1;bool removed=false;
    struct {struct {struct {char sun_path[32]="fixture-owned-path";} un;} addr;} info;
    void ssl_close(){observe("ssl");ssl=nullptr;if(ssl_hook)ssl_hook();}
};
static int unlink(const char*p){observe("unlink:"+std::string(p));return 0;}
static int close(int fd){observe("close:"+std::to_string(fd));return close_result;}
static int swoole_event_del(Socket*s){observe("event-delete");s->removed=true;if(event_hook)event_hook();return 0;}
static void swoole_timer_del(TimerNode*t){observe("timer-delete:"+std::to_string(t->id));if(timer_hook)timer_hook();}
'''
    facade=r'''
struct Client {
    Socket *socket=nullptr;bool open_ssl=false;
    void *ssl_context=nullptr;TimerNode *timer=nullptr;
    bool *destroyed=nullptr;
    std::function<void(Client*)> onClose;
#ifdef SELECTED_STATE
    // The selected Client's flags are Rust's (#439); scenarios set and read them the same way.
    std::unique_ptr<swr_v1_clients_state, decltype(&swr_v1_clients_state_free)> state_{swr_v1_clients_state_new(false), swr_v1_clients_state_free};
    bool is_closed() const{return swr_v1_clients_flag(state_.get(),SWR_CLIENTS_CLOSED);}
    bool is_active() const{return swr_v1_clients_flag(state_.get(),SWR_CLIENTS_ACTIVE);}
    bool is_async() const{return swr_v1_clients_flag(state_.get(),SWR_CLIENTS_ASYNC);}
    void set_closed(bool v){swr_v1_clients_set_flag(state_.get(),SWR_CLIENTS_CLOSED,v);}
    void set_active(bool v){swr_v1_clients_set_flag(state_.get(),SWR_CLIENTS_ACTIVE,v);}
    void set_async(bool v){swr_v1_clients_set_flag(state_.get(),SWR_CLIENTS_ASYNC,v);}
#else
    bool closed=false,async=false,active=false;
    bool is_closed() const{return closed;}
    bool is_active() const{return active;}
    bool is_async() const{return async;}
    void set_closed(bool v){closed=v;}
    void set_active(bool v){active=v;}
    void set_async(bool v){async=v;}
#endif
    ~Client(){observe("destroy");if(socket&&is_async())socket->object=nullptr;if(destroyed)*destroyed=true;}
    int close();
};
static std::string run(unsigned bits,unsigned scenario,int result){
    effects.clear();ssl_hook={};event_hook={};timer_hook={};close_result=result;
    Socket first,second;second.fd=456;TimerNode timer1{1},timer2{2};bool destroyed=false;
    auto *client=new Client;client->destroyed=&destroyed;
    client->socket=(bits&1)?&first:nullptr;first.object=second.object=client;
    client->set_closed(bits&2);client->open_ssl=bits&4;client->ssl_context=(bits&8)?&timer1:nullptr;
    first.ssl=(bits&16)?&timer1:nullptr;first.socket_type=(bits&32)?SW_SOCK_UNIX_DGRAM:1;
    client->set_async(bits&64);first.removed=bits&128;client->timer=(bits&256)?&timer1:nullptr;client->set_active(bits&512);
    probe=[&]{
        if(destroyed)return std::string("deleted");
        std::ostringstream s;s<<client->is_closed()<<client->is_active()<<client->is_async()<<":"<<(client->timer?client->timer->id:0)<<":"<<(client->socket?client->socket->fd:0);return s.str();
    };
    if(scenario&32)event_hook=[&]{client->set_active(false);client->timer=&timer2;};
    if(scenario&64)timer_hook=[&]{client->timer=&timer2;};
    if(scenario&128)ssl_hook=[&]{client->set_async(false);};
    client->onClose=[&](Client*c){
        observe("callback");
        if(scenario&1)first.object=nullptr;
        if(scenario&4)c->socket=&second;
        if(scenario&16){const int nested=c->close();observe("reenter:"+std::to_string(nested));}
        if(scenario&8)throw std::runtime_error("native close callback");
        // Test explicit deletion only where the original async Socket custody
        // keeps its saved object-null observation valid. Other cases stay live.
        if((scenario&2)&&c->is_async())delete c;
    };
    int returned=17;std::string exception;
    try{returned=client->close();}catch(const std::runtime_error&e){exception=e.what();}
    std::ostringstream result_trace;result_trace<<returned<<":"<<exception<<":"<<destroyed<<":"<<first.fd<<":"<<second.fd<<":"<<(first.object==nullptr)<<":"<<(second.object==nullptr)<<":"<<first.removed;
    if(!destroyed)result_trace<<":"<<probe();
    for(const auto&e:effects)result_trace<<"|"<<e;
    probe={};ssl_hook={};event_hook={};timer_hook={};
    if(!destroyed)delete client;
    return result_trace.str();
}
'''
    driver=r'''
int main(){size_t count=0;
    for(unsigned bits=0;bits<1024;bits++)for(unsigned scenario:{0,1,2,4,8,16,32,64,128,17,66})for(int result:{-1,0}){
        auto expected=native::run(bits,scenario,result),actual=rust::run(bits,scenario,result);
        if(expected!=actual){std::cerr<<"mismatch bits="<<bits<<" scenario="<<scenario<<"\n";return 1;}++count;
    }
    std::cout<<count<<"\n";
}
'''
    # Separate class declarations, common native effect hooks and trace recorder.
    # run() follows each actual body so its own Client type drives callbacks.
    at=facade.index('static std::string run(');decl=facade[:at];runner=facade[at:]
    cpp=out/'actual_lifecycle.cpp';cpp.write_text(prelude+'\nnamespace native {\n'+decl+native+'\n'+runner+'\n}\n#define SELECTED_STATE\nnamespace rust {\n'+decl+rust+'\n'+runner+'\n}\n'+driver);exe=out/'actual_lifecycle';flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
    gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',cpp,archive,'-lpthread','-ldl','-lm','-o',exe]);cases=int(gate.run([exe]).strip())
    report=dict(passed=True,cases=cases,scope=__doc__,pin=gate.PIN,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
