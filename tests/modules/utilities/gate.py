#!/usr/bin/env python3
"""Pinned actual-body utility differential; only defined Austin inputs are compared."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
from tools.build_upstream import COMMIT as PIN
def asan_imports(archive):
    import re
    output=subprocess.check_output(['nm','-u',str(archive)],stderr=subprocess.STDOUT,text=True)
    imports=sorted(set(re.findall(r'\b__asan_(?:report|load|store)\w*',output)))
    if not imports:raise ValueError('Archive has no Rust AddressSanitizer instrumentation imports')
    return imports

def oracle(source):
    def original(path):return subprocess.check_output(['git','-C',str(source),'show',f'{PIN}:{path}'],text=True)
    misc=original('src/core/misc.cc');log=original('src/core/log.cc')
    body=misc[misc.index('uint64_t swoole_hash_php'):]
    pretty=log[log.index('std::string Logger::get_pretty_name'):log.index('bool Logger::open')].replace('Logger::get_pretty_name','pretty')
    header=original('include/swoole_log.h')
    enums=header[header.index('enum swLogLevel'):header.index('namespace swoole')]
    clamp=log[log.index('    if (level < SW_LOG_DEBUG)',log.index('void Logger::set_level')):log.index('\n}',log.index('void Logger::set_level'))]
    rotation=log[log.index('    const char *fmt;',log.index('std::string Logger::gen_real_file')):log.index('    size_t l_data_str',log.index('std::string Logger::gen_real_file'))]
    label=log[log.index('    switch (level)',log.index('void Logger::put')):log.index('    auto now =',log.index('void Logger::put'))]
    pretty += enums + '\nint log_level(int level) { int log_level;\n' + clamp + '\nreturn log_level; }\n'
    pretty += 'const char *log_rotation(int log_rotation) {\n' + rotation + '\nreturn fmt; }\n'
    pretty += 'const char *log_label(int level) { const char *level_str;\n' + label + '\nreturn level_str; }\n'
    base=original('src/core/base.cc')
    snprintf=base[base.index('size_t sw_snprintf('):base.index('size_t sw_vsnprintf(')]
    line=log[log.index('    size_t n = sw_snprintf(log_str,'):log.index('    lock.lock();',log.index('    size_t n = sw_snprintf(log_str,'))]
    pretty += '\n#define sw_unlikely(x) (x)\n' + snprintf + '\n#undef sw_unlikely\n'
    pretty += '#define SW_LOG_BUFFER_SIZE capacity\nsize_t log_line(char *log_str, size_t capacity, const char *date_str, int l_data_str, char worker_symbol, int worker_pid, int worker_id, int level, const char *content, int length) { const char *level_str=log_label(level);\n' + line + '\nreturn n; }\n#undef SW_LOG_BUFFER_SIZE\n'
    micros=log[log.index('        l_data_str += sw_snprintf('):log.index('    }',log.index('        l_data_str += sw_snprintf('))]
    pretty += '#define SW_LOG_DATE_STRLEN capacity\nsize_t log_micros(char *date_str, size_t capacity, long long now_us) { long long now_sec=0; size_t l_data_str=0;\n' + micros + '\nreturn l_data_str; }\n#undef SW_LOG_DATE_STRLEN\n'
    return body+'\n'+pretty

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',default=str(ROOT/'target/reports/utilities.json'))
    parser.add_argument('--sanitize',action='store_true')
    parser.add_argument('--rust-asan',action='store_true',help='Declare separately compiled Rust ASan archive; requires verified imports')
    args=parser.parse_args();args.archive=args.archive.resolve(strict=True)
    if args.rust_asan and not args.sanitize:parser.error('--rust-asan requires --sanitize')
    extracted=oracle(args.source)
    report={'pin':PIN,'scope':'Pinned log microseconds and log-line bytes/truncation/precision and logger level/clamp/rotation and exact LP64 signed/unsigned-char hashes and pretty-name bodies; native thread/shared-fork atomic witnesses. Binary Austin inputs excluded due pinned signed-shift undefined behavior. C++ sanitizer only; Rust not instrumented.','results':[],'passed':False}
    report['rust_asan_declared']=args.rust_asan
    if args.rust_asan:
        report['rust_asan_imports']=asan_imports(args.archive)
        report['scope']=report['scope'].replace('Rust not instrumented.','Rust ASan declared and imports verified; precompiled std not instrumented.')
    with tempfile.TemporaryDirectory(prefix='swr-utils-') as temp:
        tree=Path(temp);(tree/'oracle.inc').write_text(extracted)
        for mode in ['signed','unsigned']:
            binary=tree/mode
            command=['c++','-std=c++17','-O2',f'-f{mode}-char','-Wall','-Wextra','-Werror','-Wno-implicit-fallthrough','-I'+str(tree),'-I'+str(ROOT/'native/utilities'),str(Path(__file__).with_name('gate.cc')),str(args.archive),'-lm','-o',str(binary)]
            if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
            if args.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
            result=run_isolated(command,timeout=60)
            row={'char':mode,'compile':command,'compile_stderr':result.stderr,'compile_exit':result.returncode};report['results'].append(row)
            if result.returncode:write_report(args.output,report);print(result.stderr);return 1
            result=run_isolated([str(binary)],timeout=30);row.update({'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
            if result.returncode:write_report(args.output,report);print(result.stdout+result.stderr);return 1
            row['observations']=json.loads(result.stdout)
    report['passed']=True;write_report(args.output,report);print(json.dumps(report['results']));return 0
if __name__=='__main__':sys.exit(main())
