#!/usr/bin/env python3
"""Actual lock constructors and Rust init, faulted only at native pthread boundaries; ownership gate."""
import argparse
import errno
import json
from pathlib import Path
import sys
import subprocess
import overlay
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report




def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-asan',action='store_true');a=p.parse_args();overlay.SOURCE=a.source
    if a.rust_asan and (not a.sanitize or '__asan_report_' not in subprocess.check_output(['nm','-u',str(a.archive)],text=True,stderr=subprocess.DEVNULL)):p.error('Rust ASan requires instrumented archive imports and native sanitizer flag')
    folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True,exist_ok=True)
    support='''#pragma once
#include <cstdint>
#include <cerrno>
#include <cstddef>
#include <pthread.h>
#include <unistd.h>
#include <functional>
using sw_atomic_t=volatile uint32_t;
struct Pool { void *alloc(size_t);void free(void *); };
inline Pool *sw_mem_pool(){static Pool pool;return &pool;}
'''
    (folder/'support.h').write_text(support)
    header=overlay.original('include/swoole_lock.h').replace('#include "swoole_memory.h"','#include "support.h"')
    (folder/'swoole_lock.h').write_text(header);(folder/'reference.h').write_text(header.replace('namespace swoole','namespace reference'))
    base=overlay.original('src/core/base.cc');wait=base[base.index('bool sw_wait_for('):base.index('\nint swoole_itoa')]
    upstream='namespace reference {\n'+wait+'}\n';ported='namespace swoole {\n'+wait+'}\n'
    for name in ['mutex','rw_lock','spin_lock']:
        path='src/lock/'+name+'.cc';upstream+=overlay.original(path).replace('#include "swoole_lock.h"','#include "reference.h"').replace('namespace swoole','namespace reference')+'\n';ported+=overlay.generated()[path]+'\n'
    (folder/'original.inc').write_text(upstream);(folder/'ported.inc').write_text(ported)
    command=['c++','-std=c++17','-O1','-UNDEBUG','-DHAVE_RWLOCK','-DSWOOLE_RS_LOCKS','-I'+str(folder),'-I'+str(ROOT/'native/locks'),str(Path(__file__).resolve().with_suffix('.cc')),str(a.archive.resolve()),'-lpthread','-ldl','-lm','-o',str(folder/'constructor')]
    if sys.platform=='linux':command+=['-DHAVE_SPINLOCK','-lrt','-lutil']
    if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
    report={'scope':__doc__,'pin':overlay.PIN,'compile':command,'passed':False,'native_baseline_passed':False,'full_original_gate_passed':False,'rust_instrumented':a.rust_asan,'native_instrumented':a.sanitize}
    require_build_space(ROOT);r=run_isolated(command,timeout=90);report.update(compile_exit=r.returncode,compile_stderr=r.stderr)
    if not r.returncode:
        r=run_isolated([str(folder/'constructor')],timeout=30);report.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr)
        if not r.returncode:
            all_rows=[json.loads(line)for line in r.stdout.splitlines()]
            rows=[row for row in all_rows if not row.get('direct') and row['stage']==0];report['observations']=rows
            errors=[row for row in all_rows if not row.get('direct') and row['stage']!=0];report['first_error_observations']=errors
            for row in errors:
                row['passed']=row['engine']=='rust' and row['live']==0 and row['threw']==1 and row['code']==errno.EBUSY and row['init_calls']==0 and row['attr_init_calls']==1 and row['attr_destroyed']==int(row['stage']==2) and row['shared_calls']==int(row['stage']==2) and row['message'].startswith('pthread_'+('mutex' if row['kind']==3 else 'rwlock')+'_init() failed:')
            report['first_error_complete']=len(errors)==6 and len({(row['kind'],row['shared'],row['stage']) for row in errors})==6
            report['first_error_passed']=report['first_error_complete'] and all(row['passed'] for row in errors)
            report['first_error_native_baseline']='Not executed: original continues after failed attribute init; source-only unsafe-domain evidence, not a native parity pass'
            direct=[row for row in all_rows if row.get('direct')];report['direct_abi_observations']=direct
            for row in direct:
                row['passed']=row['result']=={0:errno.ENOMEM,1:errno.EAGAIN,2:errno.ENOTSUP}[row['stage']] and row['errno']==errno.EBUSY and row['allocated']==0 and row['released']==0 and row['init_calls']==int(row['stage']==0) and row['attr_init_calls']==int(row['kind']!=5) and row['shared_calls']==int(row['kind']!=5 and row['shared'] and row['stage']!=1) and row['attr_destroyed']==int(row['kind']!=5 and row['stage']!=1)
            report['direct_abi_complete']=len(direct)==(12 if sys.platform=='linux' else 10) and len({(row['kind'],row['shared'],row['stage']) for row in direct})==len(direct)
            report['direct_abi_passed']=report['direct_abi_complete'] and all(row['passed'] for row in direct)
            for row in rows:
                row['ownership_passed']=row['live']==0 and row['attr_destroyed']==int(row['kind']!=5)
                row['result_passed']=row['init_calls']==1 and row['threw']==row['failed_init'] and (row['code']==errno.EBUSY if row['failed_init'] else row['code']==0)
            native={(row['kind'],row['shared'],row['failed_init']):row for row in rows if row['engine']=='upstream'}
            report['exception_results_match']=all(all(row[key]==native[(row['kind'],row['shared'],row['failed_init'])][key] for key in ['threw','code','message']) for row in rows if row['engine']=='rust')
            report['native_baseline_passed']=all(row['ownership_passed'] and row['result_passed'] for row in rows if row['engine']=='upstream')
            report['expected_row_count']=24 if sys.platform=='linux' else 16
            report['complete_inventory']=len(rows)==report['expected_row_count'] and len({(r['engine'],r['kind'],r['shared'],r['failed_init']) for r in rows})==report['expected_row_count']
            report['passed']=report['direct_abi_passed'] and report['first_error_passed'] and report['complete_inventory'] and report['exception_results_match'] and all(row['ownership_passed'] and row['result_passed'] for row in rows if row['engine']=='rust')
    write_report(a.output,report);print(json.dumps({'passed':report['passed'],'native_baseline_passed':report['native_baseline_passed'],'rows':len(report.get('observations',[])),'compile_stderr':report['compile_stderr']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
