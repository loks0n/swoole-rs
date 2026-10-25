#!/usr/bin/env python3
"""Singular Rust pool + real native RAII adapter, FIFO/binary keys/fork/teardown.

This is native adapter/container proof, not whole Zend/PHP/socket lifetime or
native shutdown-allocation parity. Fault builds inject logical allocation sites,
not a claim about matching physical native allocator topology.
"""
import argparse
import json
from pathlib import Path
import gate
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--sanitize',action='store_true')
    p.add_argument('--rust-sanitized',action='store_true');p.add_argument('--faults',action='store_true',help='Additional private cfg(test) archive for injected allocation prefixes')
    a=p.parse_args();out=a.output.parent/(a.output.stem+'-artifacts');out.mkdir(parents=True,exist_ok=True);gate.LOG=out/'commands';gate.LOG.mkdir(exist_ok=True)
    if a.rust_sanitized and not (a.archive and a.sanitize):p.error('--rust-sanitized requires --archive and --sanitize')
    archive=a.archive or out/'libclients.a'
    if not a.archive:gate.run(['rustc','--edition','2024','--crate-type','staticlib','-O','-C','panic=abort',ROOT/'crates/clients/src/lib.rs','-o',archive])
    scratch=out/'patched';scratch.mkdir(exist_ok=True)
    for path in gate.overlay_manifest()['upstream_paths']:
        dest=scratch/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']))
    gate.apply_overlay(scratch,out);selected=(scratch/'ext-src/swoole_client.cc').read_text()
    for proof in ['static SwooleRustClientPool long_connections;','long_connections.state(conn_key)','long_connections.take(conn_key)','long_connections.remove_empty(cli->server_id)','long_connections.push(cli->server_id, cli)']:
        if proof not in selected:raise ValueError('Missing actual singular-pool caller: '+proof)
    if 'std::queue' in selected or 'std::unordered_map' in selected:raise ValueError('Native duplicate persistent registry remains')
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else []
    fixture=Path(__file__).with_name('pool_witness.cpp');exe=out/'actual_pool'
    gate.run(['c++','-std=c++17','-O1',*flags,'-I',ROOT/'native/clients',fixture,archive,'-lpthread','-ldl','-lm','-o',exe])
    result=json.loads(gate.run([exe]));report=dict(passed=True,scope=__doc__,pin=gate.PIN,results=result,native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized)
    if a.faults:
        fault_archive=out/'libclients-test-only.a';fault_exe=out/'actual_pool-faults'
        gate.run(['rustc','--edition','2024','--crate-type','staticlib','--cfg','test','-O','-C','panic=abort',ROOT/'crates/clients/src/lib.rs','-o',fault_archive])
        gate.run(['c++','-std=c++17','-O1','-DSWR_CLIENTS_POOL_TEST_ALLOCATION=1',*flags,'-I',ROOT/'native/clients',fixture,fault_archive,'-lpthread','-ldl','-lm','-o',fault_exe])
        report['private_test_only_faults']=dict(rust_sanitized=False,results=json.loads(gate.run([fault_exe])),scope='Separate cfg(test) archive, not the selected production archive; logical injection only')
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
