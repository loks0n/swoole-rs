#!/usr/bin/env python3
"""Positive actual rewrite callers with sole Rust rule storage, no server/network execution."""
import argparse
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, sha, body, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--prepare-binary',type=Path,help='Prepare immutable optimized body-model artifacts; run only untimed controls')
    parser.add_argument('--output', default='target/reports/http-rewrite-store.json')
    args = parser.parse_args()
    if args.prepare_binary:
        retained=[Path(args.output),args.prepare_binary,args.prepare_binary.with_suffix('.a'),args.prepare_binary.with_suffix('.sources.tar.gz')]
        if any(p.exists() for p in retained):parser.error('Refusing existing immutable preparation output')
    report = {'passed': False, 'full_gate_passed': False, 'pin': PIN,
              'scope': 'Actual positive add/apply plus sole Rust catalog; no socket/PHP/allocation-failure/lifetime/fork/performance credit',
              'unrun': ['invalid regex', 'injected failures', 'random rules', 'processes', 'external SDK ABI', 'performance'],
              'checks': [], 'timed': False, 'measurement_authorized': False, 'prepared': False}
    def checked(command, name):
        free = shutil.disk_usage(ROOT).free
        row = {'name': name, 'command': list(map(str, command)), 'free_bytes': free, 'guard_bytes': 4*1024**3}
        report['checks'].append(row)
        if free < 4*1024**3:
            row['blocked'] = 'unchanged disk guard'; write_report(args.output, report); return False
        value = run_isolated(list(map(str, command)), timeout=60)
        row.update(returncode=value.returncode, stdout=value.stdout, stderr=value.stderr)
        if value.returncode:
            write_report(args.output, report); return False
        return True
    with tempfile.TemporaryDirectory(prefix='swr-rewrite-store-') as temporary:
        tree = Path(temporary)
        report['archive_sha256'] = sha(args.archive)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        path = tree/'src/server/static_handler.cc'
        original = path.read_text()
        apply_http_patch(tree, ROOT/'migration/patches/http/0002-static-ranges.patch', report)
        selected = path.read_text()
        # The same immutable positive inputs feed actual pinned and selected
        # bodies. Minimal Native handler models only URL publication.
        prefix = '''#include <string>
#include <vector>
#include <memory>
#include <regex>
#include <stdexcept>
#include <iostream>
#include <cstring>
#include "swoole_rs_http.h"
#include "swoole_rs_http_rewrite_store.h"
namespace swoole { namespace http_server {
struct RewriteRule { std::string pattern,replacement; bool is_regex; };
}}
'''
        stubs = '''namespace http_server {
using RewriteRule=::swoole::http_server::RewriteRule;
struct StaticHandler {
 std::string url,original;unsigned publications=0;
 explicit StaticHandler(const std::string &s):url(s),original(s){}
 const std::string &get_request_url()const{return url;}
 void set_request_url(const std::string &s){++publications;url=s;}
};
}
inline bool starts_with(const std::string &value,const std::string &prefix){return value.compare(0,prefix.size(),prefix)==0;}
'''
        parts = [prefix, 'namespace swoole { namespace http_server {', *[body(selected, signature) for signature in ['void RewriteRules::append(', 'swr_v2_http_rewrite_record RewriteRules::inspect(', 'int32_t RewriteRules::advance(swr_v2_http_rewrite_state *', 'int32_t RewriteRules::advance(swr_v2_http_context *', 'std::string RewriteRules::text(', 'int32_t RewriteRules::literal(size_t index, const std::string &', 'int32_t RewriteRules::literal(size_t index, swr_v2_http_context *', 'RewriteRule RewriteRules::at(']], '}}']
        for name, text, field in [('reference', original, 'std::shared_ptr<std::vector<http_server::RewriteRule>>'), ('selected', selected, '::swoole::http_server::RewriteRules')]:
            parts += ['namespace '+name+' {', stubs,
                      'struct Server {'+field+' rewrite_rules; void add_rewrite_rule(const std::string &,const std::string &); bool apply_rewrite_rules(http_server::StaticHandler *);};',
                      body(text, 'void Server::add_rewrite_rule('), body(text, 'bool Server::apply_rewrite_rules('), '}']
        parts += [r'''
using Rules=std::vector<std::pair<std::string,std::string>>;
#ifdef SWR_REWRITE_PREPARED
#include "rewrite_store_workloads.h"
#endif
int main(int argc,char **argv){
#ifdef SWR_REWRITE_PREPARED
 if(argc>1)return rewrite_workload_command(argc,argv);
#else
 (void)argc;(void)argv;
#endif
 size_t cases=0;
 const std::vector<Rules> rules={ {},{{"",""}},{{"","/fallback"}},{{"/a","/b"}},{{"/a","/a"}},{{"/a","/first"},{"/a","/second"}},{{"~^/a$~","/regex"},{"/","/literal"}},{{"~a~","a"},{"","fallback"}},{{"~~","x"}},{{"~(a)(b)~","$2/$1"}},{{"~","/literal"}},{{std::string("/a\0",3),std::string("/b\0",3)}} };
 const std::vector<std::string> urls={"","/","/a","/a/b","/ab","/aa",std::string("/a\0tail",7),std::string(4096,'a')};
 for(const auto &url:urls)for(const auto &declarations:rules){
  reference::Server a;selected::Server b;
  for(const auto &r:declarations){a.add_rewrite_rule(r.first,r.second);b.add_rewrite_rule(r.first,r.second);}
  if((a.rewrite_rules?a.rewrite_rules->size():0)!=b.rewrite_rules.size())throw std::runtime_error("count");
  for(size_t i=0;i<declarations.size();++i){const auto &x=(*a.rewrite_rules)[i];const auto y=b.rewrite_rules.at(i);if(x.pattern!=y.pattern||x.replacement!=y.replacement||x.is_regex!=y.is_regex)throw std::runtime_error("classification/order");}
  reference::http_server::StaticHandler x(url);selected::http_server::StaticHandler y(url);
  const bool rx=a.apply_rewrite_rules(&x),ry=b.apply_rewrite_rules(&y);
  if(rx!=ry||x.url!=y.url||x.original!=y.original||x.publications!=y.publications)throw std::runtime_error("rewrite/publication");
  ++cases;
 }
 reference::Server a;selected::Server b;
 if(a.apply_rewrite_rules(nullptr)||b.apply_rewrite_rules(nullptr))throw std::runtime_error("empty short circuit");
 std::cout<<"{\"positive_cases\":"<<cases<<",\"empty_short_circuit\":true}\n";
}
''']
        source = tree/'gate.cc'; source.write_text('\n'.join(parts))
        binary = tree/'gate'
        flags=['-O3','-DNDEBUG','-DSWR_REWRITE_PREPARED','-I'+str(Path(__file__).parent),'-I'+str(ROOT/'native/include')] if args.prepare_binary else ['-O1']
        command = ['c++', '-std=c++14', *flags, '-g', '-DSWOOLE_RS_HTTP_REWRITE_STORE=1', '-I'+str(ROOT/'native/http'), str(source), str(args.archive), '-o', str(binary)]
        # Mixed Rust/Native ASan is deliberately not selected here. Existing
        # platform-incompatible sanitizer outcomes remain separate receipts.
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil', '-lm']
        if args.prepare_binary:
            if not checked(['c++','--version'],'compiler_identity'):return 1
        if not checked(command, 'compile'): return 1
        report['binary_sha256'] = sha(binary)
        names = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        required = ['swr_v2_http_rewrite_store_'+suffix for suffix in ['add', 'read', 'count', 'drop', 'literal', 'context_literal', 'text', 'advance', 'context_advance']]
        report['required_symbols_present'] = {name: name in names for name in required}
        if not all(report['required_symbols_present'].values()): write_report(args.output, report); return 1
        if not checked([str(binary)], 'positive_actual_bodies'): return 1
        report['outcome'] = json.loads(report['checks'][-1]['stdout'].splitlines()[-1])
        if args.prepare_binary:
            if not checked([str(binary),'--check-workloads'],'untimed_prepared_workloads'):return 1
            report['prepared_outcome']=json.loads(report['checks'][-1]['stdout'].splitlines()[-1])
            if report['prepared_outcome'].get('timed') is not False or report['prepared_outcome'].get('verified') is not True:raise ValueError('Expected untimed workload checks')
            args.prepare_binary.parent.mkdir(parents=True,exist_ok=True)
            archive_copy=args.prepare_binary.with_suffix('.a');capsule=args.prepare_binary.with_suffix('.sources.tar.gz')
            shutil.copy2(binary,args.prepare_binary);shutil.copy2(args.archive,archive_copy)
            with tarfile.open(capsule,'w:gz') as retained:
                retained.add(source,arcname='native/actual-bodies.cc')
                for name,text in [('original.cc',original),('selected.cc',selected)]:
                    saved=tree/name;saved.write_text(text);retained.add(saved,arcname='native/'+name)
                for path in [ROOT/'native/http',ROOT/'native/include/swoole_rs.h',ROOT/'crates/ffi',ROOT/'crates/http',ROOT/'crates/base64',ROOT/'migration/patches/http',ROOT/'Cargo.toml',ROOT/'Cargo.lock',Path(__file__),Path(__file__).parent/'rewrite_store_workloads.h',Path(__file__).parent/'gate.py']:
                    retained.add(path,arcname='repo/'+str(path.relative_to(ROOT)))
            if sha(archive_copy)!=report['archive_sha256'] or sha(args.prepare_binary)!=report['binary_sha256']:raise ValueError('Prepared artifact identity differs')
            report['archive_optimization']='Supplied archive; use its exact build receipt, never infer optimization from bytes'
            report['prepared_workloads']=['literal-hit','literal-miss','regex-hit','regex-miss','ordered-16','configure-16']
            report['source_capsule_scope']='Actual extracted bodies, owned Native/Rust source and overlays; external compiler/SDK/runtime closure is not self-contained'
            report['prepared']=True
        report['passed'] = True; write_report(args.output, report)
        print(json.dumps(report['outcome']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
