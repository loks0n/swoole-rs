#!/usr/bin/env python3
"""Actual pinned static context bodies versus sole-Rust V2; normal effects only."""
import argparse
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_static_header, prepare_index_buffer, add_archive_arguments, prepare_archive, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_hybrid import apply_patch_verified


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    add_archive_arguments(parser)
    parser.add_argument('--static-config',action='store_true',help='Actual sole Rust root/location/index owner; requires paired shared Server declarations')
    parser.add_argument('--rewrite-store',action='store_true',help='Actual sole Rust rewrite catalog; requires integrated shared Server field')
    parser.add_argument('--output',default='target/reports/http-context.json')
    args=parser.parse_args();local=Path(__file__).resolve().parent
    patch=ROOT/'migration/patches/http/0002-static-ranges.patch'
    report={'pin':PIN,'scope':__doc__,'passed':False,'full_gate_passed':False,
        'static_config':args.static_config,'rewrite_store':args.rewrite_store,'rust_instrumented':args.rust_sanitize,'rust_std_instrumented':False,
        'unrun_profiles':['previous private V2 core/reference adapter assertions','native allocation/error/partial/lifetime/reentry profiles',
            'full configured PHP/original/IO','performance','other platforms/locales']}
    def checked(command,label,timeout=60):
        free=shutil.disk_usage(ROOT).free
        if free<4*1024**3:
            report[label]={'command':command,'blocked':'unchanged disk guard','free_bytes':free,'guard_bytes':4*1024**3}
            write_report(args.output,report);return False
        result=run_isolated(command,timeout=timeout)
        report[label]={'command':command,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        if result.returncode:
            write_report(args.output,report);print(result.stderr,file=sys.stderr)
            return False
        return True
    with tempfile.TemporaryDirectory(prefix='swr-http-context-') as temporary:
        tree=Path(temporary)
        if not prepare_archive(args,tree,report):write_report(args.output,report);return 1
        data=subprocess.check_output(['git','-C',str(args.source),'archive',PIN,'include','src/server/static_handler.cc','src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path=tree/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
        path=tree/'src/server/static_handler.cc';original=path.read_text()
        original_header=(tree/'include/swoole_static_handler.h').read_text()
        protocol=(tree/'src/protocol/http.cc').read_text()
        apply_http_patch(tree, patch, report)
        selected=path.read_text()
        apply_static_header(tree,report);prepare_index_buffer(tree,report)
        if args.rewrite_store or args.static_config:
            manifest=ROOT/'migration/patches/integration/manifest.json'
            for entry in json.loads(manifest.read_text())['patches']:
                if entry['upstream_paths']==['include/swoole_server.h']:
                    report.setdefault('shared_header_patch_application',[]).append(apply_patch_verified(tree,manifest.parent/entry['path'],entry['upstream_paths'],entry['sha256']))
            if args.static_config and 'http_server::StaticConfig static_config_' not in (tree/'include/swoole_server.h').read_text():
                report['blocked']='Concrete shared Server StaticConfig field absent';write_report(args.output,report);return 1
            if args.rewrite_store and 'http_server::RewriteRules rewrite_rules' not in (tree/'include/swoole_server.h').read_text():
                report['blocked']='Concrete shared Server rewrite field absent';write_report(args.output,report);return 1
        flags=['-std=c++17','-DSWOOLE_RS_HTTP','-O1','-g','-I'+str(tree/'include'),'-I'+str(ROOT/'native/http'),'-I'+str(local),'-I'+str(tree),'-fsanitize=address,undefined','-fno-sanitize-recover=all']
        if args.static_config:flags+=['-DSWOOLE_RS_HTTP_STATIC_CONFIG=1']
        if args.rewrite_store:flags+=['-DSWOOLE_RS_HTTP_REWRITE_STORE=1']
        flags+=shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True))
        if not checked(['c++',*['-std=c++14' if flag=='-std=c++17' else flag for flag in flags],'-c',str(path),'-o',str(tree/'static.o')],'whole_native_translation_unit'):return 1
        native_base=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':src/core/base.cc'],text=True)
        server='''struct Server {
 std::string root="/root";bool http_autoindex=false;long timezone_=0;
 std::shared_ptr<std::unordered_set<std::string>> locations=std::make_shared<std::unordered_set<std::string>>();
 std::shared_ptr<std::vector<std::string>> http_index_files;
 std::shared_ptr<std::vector<RewriteRule>> rewrite_rules;
 const std::string &get_document_root()const{return root;}
 bool apply_rewrite_rules(StaticHandler *);
};\n'''
        candidate_server=server.replace('std::shared_ptr<std::vector<RewriteRule>> rewrite_rules;', 'RewriteRulesField rewrite_rules;')
        if args.static_config:
            candidate_server='''struct Server {
 bool http_autoindex=false;long timezone_=0;
 RewriteRulesField rewrite_rules;
 swoole::http_server::StaticConfig configuration;
 Server(){configuration.root_finish("/root");configuration.initialize();}
 const swoole::http_server::StaticConfig &static_files()const{return configuration;}
 swoole::http_server::StaticConfig &static_files(){return configuration;}
 bool apply_rewrite_rules(StaticHandler *);
};\n'''
            report['static_config_fixture_scope']='Selected fixture uses actual typed configuration owner/admission, not legacy direct vector mutation; empty vector control maps to no index admissions. Public old-field compatibility remains unsupported.'
        original_class=body(original_header,'class StaticHandler')+';\n'
        typed=body((ROOT/'native/http/swoole_rs_http_static_v2.h').read_text(),'class StaticHandlerV2')+';\n'
        headers='#pragma once\n#include "context_oracle.h"\n#include "swoole_rs_http_rewrite_store.h"\n#include "swoole_rs_http_static_config.h"\n'
        headers+='namespace upstream_context {using swoole::starts_with; class StaticHandler;\n'+server+original_class+'}\n'
        headers+='namespace candidate_context {using StaticHandler=swoole::http_server::StaticHandler;using StaticConfig=swoole::http_server::StaticConfig;using RewriteRulesField=swoole::http_server::RewriteRulesField;\n'+candidate_server+typed+'}\n'
        (tree/'context_candidate.h').write_text(headers)
        old_signatures=re.findall(r'^((?:bool|size_t|void|std::string) StaticHandler::[^\n]+?)\s*\{',original,re.M)
        v2_signatures=re.findall(r'^((?:(?:bool|size_t|void|int32_t|uint32_t|time_t|std::string|swr_v2_http_observation|const std::string &|std::vector<swr_v2_http_static_task>)\s*)?StaticHandlerV2::[^\n{]+|StaticHandlerV2::~StaticHandlerV2\([^\n{]+)',selected,re.M)
        # Constructor spans a second signature line; body() retains its complete initializer.
        v2_signatures=['StaticHandlerV2::StaticHandlerV2(', 'StaticHandlerV2::~StaticHandlerV2(']+[signature for signature in v2_signatures if '::StaticHandlerV2(' not in signature and '::~StaticHandlerV2(' not in signature]
        report['selected_method_signatures']=v2_signatures
        assert 'core_' not in typed and 'directory_' not in typed and 'tasks_' not in typed
        report['native_context_storage_absent']=True
        report['effect_name_qualification']='Only extracted lstat calls are namespace-qualified to avoid global stat-argument ADL; production and original assertions unchanged'
        for namespace in ['upstream_context','candidate_context']:
            parts=[]
            if namespace=='upstream_context':
                parts+=[body(protocol,'static int url_htoi('),body(protocol,'size_t url_decode('),body(native_base,'std::string intersection(')]
                parts += [body(original,signature) for signature in old_signatures]
                parts += [body(original,'bool Server::apply_rewrite_rules(').replace('http_server::StaticHandler *','StaticHandler *')]
            else:
                parts += ['template<typename Handler>\n'+body(selected,'static bool conditional_file_date(')]
                parts += [body(selected,signature) for signature in ['static void append_directory_part(', 'static int32_t resume_range_header(', 'static int32_t resume_static_path(']]
                parts += [body(selected,signature) for signature in v2_signatures]
            extracted=tree/(namespace+'.cc')
            extracted.write_text('#include "context_candidate.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts).replace('lstat(',namespace+'::lstat(')+'\n}\n')
        dependency=tree/'dependencies.cc';dependency.write_text('#include "context_oracle.h"\n'+body(native_base,'size_t sw_snprintf('))
        store_sources=[]
        if args.rewrite_store:
            store_source=tree/'rewrite-store.cc'
            store_source.write_text('#include "context_candidate.h"\nnamespace swoole { namespace http_server {\n'+'\n'.join(body(selected,signature) for signature in ['void RewriteRules::append(', 'swr_v2_http_rewrite_record RewriteRules::inspect(', 'int32_t RewriteRules::advance(swr_v2_http_rewrite_state *', 'int32_t RewriteRules::advance(swr_v2_http_context *', 'std::string RewriteRules::text(', 'int32_t RewriteRules::literal(size_t index, const std::string &', 'int32_t RewriteRules::literal(size_t index, swr_v2_http_context *', 'RewriteRule RewriteRules::at('])+'\n}}\n')
            store_sources=[str(store_source)]
        binary=tree/'gate'
        command=['c++',*flags,str(tree/'upstream_context.cc'),str(tree/'candidate_context.cc'),str(dependency),str(local/'context_gate.cc'),*store_sources,str(args.archive.resolve()),'-lm','-o',str(binary)]
        if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
        if not checked(command,'compile'):return 1
        symbols=subprocess.check_output(['nm','-g',str(binary)],text=True)
        assert all(name in symbols for name in ['swr_v2_http_context_new','swr_v2_http_context_tasks','swr_v2_http_context_path','swr_v2_http_context_scan','swr_v2_http_context_index','swr_v2_http_context_page_step','swr_v2_http_context_page_emit','swr_v2_http_context_boundary','swr_v2_http_context_serve'])
        if not checked([str(binary)],'run',30):return 1
        report['outcome']=json.loads(report['run']['stdout'].splitlines()[-1]);report['passed']=True
        write_report(args.output,report);print(json.dumps(report['outcome']))
    return 0
if __name__=='__main__':sys.exit(main())
