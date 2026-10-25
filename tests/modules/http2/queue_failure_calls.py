#!/usr/bin/env python3
"""Actual Rust allocator NULL -> exported queue -> native wrapper/new_handler witness.

Only a cfg(test) archive intercepts actual Rust allocator calls; ordinary builds
contain no injection state or exports. Real host OOM is never induced.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--core-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include', action='append', default=[])
    args = parser.parse_args()
    core = json.loads(args.core_report.read_text())
    if not core['passed']:
        raise ValueError('Completed passing production core receipt required')
    sources = {str(p.relative_to(gate.ROOT)): gate.digest(p)
               for p in sorted((gate.ROOT / 'crates/http2/src').rglob('*.rs'))}
    if sources != core['rust_sources']:
        raise ValueError('Rust source identity differs from completed core')
    header = gate.ROOT / 'native/http2/rust_http2.h'
    if gate.digest(header) != core['module_header_sha256']:
        raise ValueError('Module header changed')
    work = args.output.parent / (args.output.stem + '-artifacts')
    work.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'scope': __doc__, 'upstream_commit': gate.PIN,
              'commands': [],
              'gaps': ['Actual system OOM/physical allocation timing and custom native allocators',
                       'PHP/coroutine/GC/Zend longjmp and complete selected runtime inventories',
                       'Rust sanitizer instrumentation and optimized performance']}

    def run(command):
        command = list(map(str, command))
        result = subprocess.run(command, capture_output=True, text=True)
        report['commands'].append({'command': command, 'returncode': result.returncode,
                                   'stdout': result.stdout, 'stderr': result.stderr})
        result.check_returncode()
        return result.stdout

    try:
        baseline_path = work / 'production-queue.json'
        command = [sys.executable, gate.ROOT / 'tests/modules/http2/queue_calls.py', '--source', args.source,
                   '--core-report', args.core_report, '--output', baseline_path]
        for include in args.include:
            command += ['--include', include]
        run(command)
        baseline = json.loads(baseline_path.read_text())
        if not baseline['passed']:
            raise ValueError('Production queue gate failed')
        report['production_queue_report'] = str(baseline_path.resolve())
        report['production_queue_cases'] = baseline['queue_cases']
        baseline_cpp = work / 'production-queue-artifacts/queue.cpp'
        if gate.digest(baseline_cpp) != baseline['harness_sha256']:
            raise ValueError('Production harness changed')
        archive = work / 'libhttp2-fault-fixture.a'
        run(['rustc', '--edition=2021', '--cfg', 'test', '--crate-type', 'staticlib',
             '-C', 'opt-level=2', '-C', 'panic=abort', gate.ROOT / 'crates/http2/src/lib.rs', '-o', archive])
        source = baseline_cpp.read_text()
        if source.count('int main(){') != 1:
            raise ValueError('Unexpected baseline main count')
        source = source.replace('int main(){', 'int baseline_main(){').rstrip()
        if not source.endswith('}'):
            raise ValueError('Unexpected baseline final brace')
        # Only main has C++'s implicit return0; the renamed fixture helper needs it explicitly.
        source = source[:-1] + 'return 0;\n}\n'
        source += r'''
struct FaultState {uint32_t site,failed_site,attempts,failures;};
extern "C" void sw_rs_http2_test_queue_failure_after(size_t);
extern "C" void sw_rs_http2_test_queue_fault_state(FaultState*);
static unsigned handler_mode,handler_calls;
static void native_handler(){FaultState state;sw_rs_http2_test_queue_fault_state(&state);if(state.site||state.failures!=1)std::abort();++handler_calls;effects.push_back("native_handler:rust_returned");if(handler_mode==2)throw std::runtime_error("native handler throw");}
static FaultState state(){FaultState s;sw_rs_http2_test_queue_fault_state(&s);return s;}
int main(){if(baseline_main())return 10;auto saved_handler=std::get_new_handler();size_t owner_cases=0,growth_cases=0,unpublished=0;std::vector<std::string>rows;
for(unsigned mode=0;mode<3;++mode){
 handler_mode=mode;handler_calls=0;std::set_new_handler(mode?native_handler:nullptr);sw_rs_http2_test_queue_failure_after(0);bool constructed=false,bad_alloc=false,handler_throw=false;
 try{swoole::http2::RustSendQueue<int>queue;constructed=true;if(queue.size())return 11;}catch(const std::bad_alloc&){bad_alloc=true;}catch(const std::runtime_error&){handler_throw=true;}
 auto s=state();if(s.site||s.failed_site!=1||s.failures!=1||s.attempts!=1||constructed!=(mode==1)||bad_alloc!=(mode==0)||handler_throw!=(mode==2)||handler_calls!=(mode?1:0))return 12;
 rows.push_back("{\"kind\":\"owner\",\"mode\":"+std::to_string(mode)+",\"handlers\":"+std::to_string(handler_calls)+",\"rust_site_after_return\":"+std::to_string(s.site)+",\"failed_site\":"+std::to_string(s.failed_site)+"}");++owner_cases;sw_rs_http2_test_queue_failure_after(SIZE_MAX);
}
for(unsigned mode=0;mode<3;++mode)for(unsigned seed:{0u,1u,4u,17u,65u})for(unsigned allowed:{0u,1u,2u})for(bool wrap:{false,true}){
 if(!live.empty())std::abort();effects.clear();serial=0;allocation_failure=0;handler_mode=mode;handler_calls=0;std::set_new_handler(mode?native_handler:nullptr);FixtureSocket socket;socket.bound=true;rust::Client client;client.socket_=&socket;client.remote_settings.max_concurrent_streams=UINT32_MAX;std::deque<unsigned>expected;
 for(unsigned i=0;i<seed;++i){if(!client.send("seed",4))return 13;expected.push_back(serial-1);if(wrap&&i%3==1){auto token=client.send_queue.front_or_null();if(token->id!=expected.front())return 24;expected.pop_front();client.send_queue.pop();zend_string_release(token);}}
 sw_rs_http2_test_queue_failure_after(allowed);bool witnessed=false;size_t before=0,after=0,live_before=0;zend_string*unpublished_token=nullptr;
 for(unsigned attempt=0;attempt<2048;++attempt){before=client.send_queue.size();bool returned=false,bad_alloc=false,handler_throw=false;try{returned=client.send("fault",5);}catch(const std::bad_alloc&){bad_alloc=true;}catch(const std::runtime_error&){handler_throw=true;}
 auto s=state();if(returned)expected.push_back(serial-1);if(s.site)return 14;if(!s.failures){if(!returned||client.send_queue.size()!=before+1||live.size()!=before+1)return 15;continue;}
 witnessed=true;after=client.send_queue.size();live_before=live.size();if(s.failed_site!=2||s.failures!=1||s.attempts!=allowed+1||handler_calls!=(mode?1:0)||returned!=(mode==1)||bad_alloc!=(mode==0)||handler_throw!=(mode==2))return 16;
 if(mode==1){if(after!=before+1||live_before!=after)return 17;}else{if(after!=before||live_before!=after+1)return 18;for(auto token:live)if(token->id==serial-1)unpublished_token=token;if(!unpublished_token)return 19;++unpublished;}
 rows.push_back("{\"kind\":\"growth\",\"mode\":"+std::to_string(mode)+",\"seed\":"+std::to_string(seed)+",\"allowed_allocations\":"+std::to_string(allowed)+",\"wrap\":"+std::to_string(wrap)+",\"before\":"+std::to_string(before)+",\"after\":"+std::to_string(after)+",\"live_before_cleanup\":"+std::to_string(live_before)+",\"handlers\":"+std::to_string(handler_calls)+",\"rust_site_after_return\":"+std::to_string(s.site)+",\"failed_site\":"+std::to_string(s.failed_site)+"}");break;
 }
 if(!witnessed)return 20;auto clean_start=effects.size();client.clean_send_queue();if(effects.size()!=clean_start+expected.size())return 25;for(auto id:expected)if(effects[clean_start++]!="release:"+std::to_string(id))return 26;if(live.size()!=size_t(mode!=1))return 21;if(unpublished_token){if(!live.count(unpublished_token))return 22;zend_string_release(unpublished_token);}if(!live.empty())return 23;++growth_cases;sw_rs_http2_test_queue_failure_after(SIZE_MAX);
}
std::set_new_handler(saved_handler);std::cout<<"{\"passed\":true,\"owner_cases\":"<<owner_cases<<",\"growth_cases\":"<<growth_cases<<",\"unpublished_payload_remnants\":"<<unpublished<<",\"observations\":[";for(size_t i=0;i<rows.size();++i){if(i)std::cout<<",";std::cout<<rows[i];}std::cout<<"]}\n";
}
'''
        cpp = work / 'queue-failures.cpp'
        cpp.write_text(source)
        executable = work / 'queue-failures'
        command = ['c++', '-std=c++17', '-O1', '-fsanitize=address,undefined', '-fno-sanitize=alignment',
                   '-fno-omit-frame-pointer', '-I', gate.ROOT / 'native/http2', '-I', args.source / 'include']
        for include in args.include:
            command += ['-I', include]
        run(command + [cpp, archive, '-o', executable])
        outputs = [json.loads(line) for line in run([executable]).splitlines()]
        report['fixture_baseline'] = outputs[0]
        report['fault_witness'] = outputs[1]
        if sources != {str(p.relative_to(gate.ROOT)): gate.digest(p)
                       for p in sorted((gate.ROOT / 'crates/http2/src').rglob('*.rs'))} or gate.digest(header) != core['module_header_sha256']:
            raise ValueError('Sources changed during witness')
        report['passed'] = all(row['passed'] for row in outputs)
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    report['native_sanitizers'] = ['address', 'undefined except alignment']
    report['rust_sanitized'] = False
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'report': str(args.output), 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
