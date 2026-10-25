#!/usr/bin/env python3
"""Pinned actual helper-body comparisons; no Zend runtime/parity claim."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report
from tools.build_upstream import COMMIT as PIN


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(source,work):
    outputs={}
    environment={**os.environ,'GIT_CEILING_DIRECTORIES':str(work.parent.resolve())}
    manifest=json.loads((ROOT/'migration/patches/phphelpers/manifest.json').read_text())
    for patch in manifest['patches']:
        p=ROOT/'migration/patches/phphelpers'/patch['path']
        if sha(p)!=patch['sha256']:raise ValueError('Overlay checksum mismatch')
        for name in patch['upstream_paths']:
            raw=subprocess.check_output(['git','-C',str(source),'show',PIN+':'+name])
            path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            outputs[name]={}
        subprocess.run(['git','apply','--check',str(p)],cwd=work,env=environment,check=True,capture_output=True)
        subprocess.run(['git','apply',str(p)],cwd=work,env=environment,check=True,capture_output=True)
    return outputs


def body(text,signature):
    start=text.index(signature);end=text.index('{',start)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path);p.add_argument('--sanitize',action='store_true',help='Instrument native fixtures with address/undefined sanitizers');p.add_argument('--rust-asan',action='store_true',help='Verify supplied archive module ASan imports; requires --archive and --sanitize');p.add_argument('--rust-sanitize',action='store_true',help='Privately instrument this Rust module with ASan; prebuilt std remains uninstrumented');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.rust_asan and (not a.archive or not a.sanitize):p.error('--rust-asan requires --archive and --sanitize')
    if a.rust_sanitize and (a.archive or not a.sanitize):p.error('--rust-sanitize requires --sanitize and a privately built archive')
    output=a.output.resolve();work=output.parent/('phphelpers-'+uuid.uuid4().hex);work.mkdir(parents=True)
    report={'passed':False,'pin':PIN,'scope':__doc__,'work':str(work),'commands':[],'checks':[],
            'native_sanitizers':['address','undefined'] if a.sanitize else [],'rust_sanitized':False}
    def checkpoint():write_report(output,report)
    def run(command,timeout=90,environment=None):
        require_build_space(ROOT)
        result=run_isolated(list(map(str,command)),timeout=timeout,**({'env':environment} if environment else {}))
        report['commands'].append(dict(command=list(map(str,command)),returncode=result.returncode,stdout=result.stdout,stderr=result.stderr));checkpoint();return result
    try:
        require_build_space(ROOT)
        report['toolchains']={}
        for tool in ['rustc','c++']:
            info=subprocess.run([tool,'--version'],text=True,capture_output=True,check=True)
            report['toolchains'][tool]=info.stdout.strip()
        report['sources']=stage(a.source,work)
        if not a.archive:
            tests=work/'rust-tests'
            result=run(['rustc','--edition=2024','--test',ROOT/'crates/phphelpers/src/lib.rs','-o',tests])
            if result.returncode:raise ValueError('Rust test compilation failed')
            if run([tests]).returncode:raise ValueError('Rust policy tests failed')
        archive=a.archive.resolve() if a.archive else work/'libphphelpers.a'
        if not a.archive:
            command=['rustc','--edition=2024','--crate-type=staticlib','-C','opt-level=2',ROOT/'crates/phphelpers/src/lib.rs','-o',archive]
            if a.rust_sanitize:command+=['-Zsanitizer=address','-C','panic=abort']
            if run(command,environment={**os.environ,'RUSTC_BOOTSTRAP':'1'} if a.rust_sanitize else None).returncode:raise ValueError('Rust compilation failed')
        report['archive']=str(archive)
        if a.rust_sanitize or a.rust_asan:
            # Inspect the selected module object, avoiding older platform nm readers
            # parsing newer LLVM metadata in uninstrumented prebuilt std members.
            members=subprocess.check_output(['ar','t',str(archive)],text=True).splitlines()
            own=[name for name in members if name.startswith(('libphphelpers.lib.','swoole_rs_phphelpers.swoole_rs_phphelpers.')) and name.endswith('.rcgu.o')]
            if not own:raise ValueError('Rust module object missing from archive')
            inspected=[]
            for index,member in enumerate(own):
                obj=work/('instrumentation-'+str(index)+'.o')
                obj.write_bytes(subprocess.check_output(['ar','p',str(archive),member]))
                symbols=subprocess.check_output(['nm','-u',str(obj)],text=True,stderr=subprocess.PIPE)
                inspected.append({'member':member,'asan_load_store_imports':'__asan_report_' in symbols})
            report['rust_instrumentation']=inspected
            if not any(item['asan_load_store_imports'] for item in inspected):raise ValueError('Rust module has no ASan load/store imports')
            report['rust_sanitized']=True
        sanitizer_flags=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'] if a.sanitize else []
        original=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':ext-src/swoole_stdext.cc'],text=True)
        begin=original.index('static std::unordered_map<std::string, std::string> array_methods');end=original.index('\nstatic void move_first_element',begin)
        (work/'aliases.inc').write_text(original[begin:end]);(work/'arguments.inc').write_text(body(original,'static void move_first_element('))
        selected=(work/'ext-src/swoole_stdext.cc').read_text();(work/'selected-arguments.inc').write_text(body(selected,'static void move_first_element('))
        binary=work/'gate';command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_suffix('.cc'),archive,'-lpthread','-lm','-o',binary]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Actual argument/alias comparison compilation failed')
        result=run([binary]);report['passed']=result.returncode==0
        if not result.returncode:report['observations']=json.loads(result.stdout)
        for engine in ['reference','candidate']:
            common=(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':ext-src/php_swoole_cxx.cc'],text=True) if engine=='reference' else (work/'ext-src/php_swoole_cxx.cc').read_text())
            begin=common.index('static zend_always_inline zval *sw_zend_symtable_str_add(')
            if engine=='candidate':begin=common.index('#ifndef SWOOLE_RS_PHPHELPERS\nstatic zend_always_inline zval *sw_zend_symtable_str_add(')
            end=common.index('\nnamespace function',begin)
            extracted=common[begin:end]+'\n'+body(common,'Callable::Callable(')+'\nnamespace function {\n'+body(common,'bool call(')+'\n'+body(common,'Variable call(')+'\n}\n'
            (work/(engine+'-effects.inc')).write_text(extracted)
        effects=work/'effects'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('effects.cc'),archive,'-lpthread','-lm','-o',effects]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete native-effect fixture compilation failed')
        effect_result=run([effects]);report['passed']=report['passed'] and effect_result.returncode==0
        if not effect_result.returncode:report['effect_observations']=json.loads(effect_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            pieces=[body(content,'static void remove_all_spaces('),body(content,'static int8_t get_type('),body(content,'bool ArrayTypeValue::parse('),body(content,'static zend_string *get_array_type_def(')]
            if engine=='candidate':pieces.insert(0,body(content,'static uint8_t phphelpers_zend_kind('));pieces.insert(0,body(content,'static uint32_t phphelpers_kind('))
            (work/(engine+'-definition.inc')).write_text('\n'.join(pieces))
        definition=work/'definition'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('definition.cc'),archive,'-lpthread','-lm','-o',definition]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete type-definition fixture compilation failed')
        definition_result=run([definition]);report['passed']=report['passed'] and definition_result.returncode==0
        if not definition_result.returncode:report['definition_observations']=json.loads(definition_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            start=content.index('struct ArrayTypeValue {');end=content.index('static zend_function *fn_swoole_call_array_method',start)
            pieces=[content[start:end],body(content,'static ArrayTypeInfo *get_type_info(zend_array *array) {'),
                    body(content,'static zend_string *get_array_type_def('),body(content,'bool ArrayTypeInfo::check(')]
            if engine=='candidate':pieces.insert(0,body(content,'static uint32_t phphelpers_kind('))
            (work/(engine+'-validation.inc')).write_text('\n'.join(pieces))
        validation=work/'validation'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('validation.cc'),archive,'-lpthread','-lm','-o',validation]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete typed-validation fixture compilation failed')
        validation_result=run([validation]);report['passed']=report['passed'] and validation_result.returncode==0
        if not validation_result.returncode:report['validation_observations']=json.loads(validation_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            pieces=[body(content,'static void array_add_or_update('),body(content,'static void array_op(')]
            if engine=='candidate':
                pieces.insert(0,body(content,'static void phphelpers_mutate('))
                pieces.insert(0,body(content,'static uint32_t phphelpers_kind('))
            (work/(engine+'-mutation.inc')).write_text('\n'.join(pieces))
        mutation=work/'mutation'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('mutation.cc'),archive,'-lpthread','-lm','-o',mutation]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete mutation fixture compilation failed')
        mutation_result=run([mutation]);report['passed']=report['passed'] and mutation_result.returncode==0
        if not mutation_result.returncode:report['mutation_observations']=json.loads(mutation_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            pieces=[body(content,'static PHP_FUNCTION('+name+') {') for name in ['swoole_array_push','swoole_array_unshift','swoole_array_splice']]
            if engine=='candidate':pieces.insert(0,body(content,'static void phphelpers_builtin('))
            (work/(engine+'-builtins.inc')).write_text('\n'.join(pieces))
        builtins=work/'builtins'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('builtins.cc'),archive,'-lpthread','-lm','-o',builtins]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete builtin fixture compilation failed')
        builtins_result=run([builtins]);report['passed']=report['passed'] and builtins_result.returncode==0
        if not builtins_result.returncode:report['builtin_observations']=json.loads(builtins_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            start=content.index('struct ArrayTypeValue {');end=content.index('static zend_function *fn_swoole_call_array_method',start)
            pieces=[content[start:end],body(content,'static void remove_all_spaces('),body(content,'static int8_t get_type('),
                    body(content,'bool ArrayTypeValue::parse('),body(content,'bool ArrayTypeInfo::parse(zend_string *type_def) {')]
            if engine=='candidate':
                pieces.insert(0,body(content,'static uint8_t phphelpers_zend_kind('))
                pieces.insert(0,body(content,'static uint32_t phphelpers_kind('))
            (work/(engine+'-parse.inc')).write_text('\n'.join(pieces))
        parse=work/'parse'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('parse.cc'),archive,'-lpthread','-lm','-o',parse]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete definition-parser fixture compilation failed')
        parse_result=run([parse]);report['passed']=report['passed'] and parse_result.returncode==0
        if not parse_result.returncode:report['parse_observations']=json.loads(parse_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            pieces=[body(content,'static zval *get_array_on_opline(')]
            for begin,end in [('static int opcode_handler_array(zend_execute_data *execute_data, const ArrayFn &fn)', 'static int opcode_handler_array_assign('),
                              ('static int opcode_handler_foreach_begin(zend_execute_data *execute_data) {','static int opcode_handler_array_unset(zend_execute_data *execute_data) {'),
                              ('static int opcode_handler_array_unset(zend_execute_data *execute_data) {','static void remove_all_spaces(')]:
                pieces.append(body(content,begin))
            if engine=='candidate':pieces.insert(1,body(content,'static int phphelpers_vm('))
            (work/(engine+'-vmfacade.inc')).write_text('\n'.join(pieces))
        vmfacade=work/'vmfacade'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('vmfacade.cc'),archive,'-lpthread','-lm','-o',vmfacade]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete VM facade fixture compilation failed')
        vmfacade_result=run([vmfacade]);report['passed']=report['passed'] and vmfacade_result.returncode==0
        if not vmfacade_result.returncode:report['vmfacade_observations']=json.loads(vmfacade_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            start=content.index('static int opcode_handler_method_call(zend_execute_data *execute_data) {')
            finish=content.index('void php_swoole_stdext_minit(',start)
            pieces=[body(content,'static int opcode_handler_method_call(zend_execute_data *execute_data) {')]
            if engine=='candidate':pieces.insert(0,body(content,'static uint32_t phphelpers_kind('))
            (work/(engine+'-methodframe.inc')).write_text('\n'.join(pieces))
        methodframe=work/'methodframe'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('methodframe.cc'),archive,'-lpthread','-lm','-o',methodframe]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete method frame fixture compilation failed')
        methodframe_result=run([methodframe]);report['passed']=report['passed'] and methodframe_result.returncode==0
        if not methodframe_result.returncode:report['methodframe_observations']=json.loads(methodframe_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            tables=(original[original.index('static std::unordered_map<std::string, std::string> array_methods'):original.index('static void move_first_element(')] if engine=='reference' else
                    '')
            pieces=[tables,body(content,'static void move_first_element('),body(content,'static void call_func_move_first_arg('),body(content,'static void call_method(')]
            (work/(engine+'-invocation.inc')).write_text('\n'.join(pieces))
        invocation=work/'invocation'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('invocation.cc'),archive,'-lpthread','-lm','-o',invocation]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete method invocation fixture compilation failed')
        invocation_result=run([invocation]);report['passed']=report['passed'] and invocation_result.returncode==0
        if not invocation_result.returncode:report['invocation_observations']=json.loads(invocation_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            pieces=[body(content,signature) for signature in ['static bool is_typed_array(',
                    'static HashTable *make_typed_array(', 'static ArrayTypeInfo *get_type_info(zend_array *array) {',
                    'PHP_FUNCTION(swoole_typed_array) {','PHP_FUNCTION(swoole_array_is_typed) {']]
            (work/(engine+'-construction.inc')).write_text('\n'.join(pieces))
        construction=work/'construction'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('construction.cc'),archive,'-lpthread','-lm','-o',construction]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete construction/predicate fixture compilation failed')
        construction_result=run([construction]);report['passed']=report['passed'] and construction_result.returncode==0
        if not construction_result.returncode:report['construction_observations']=json.loads(construction_result.stdout)
        public_header=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':ext-src/php_swoole_cxx.h'],text=True)
        macro=public_header[public_header.index('#define SW_ZEND_KNOWN_STRINGS'):public_header.index('#define SW_ZSTR_KNOWN')]
        (work/'known-macro.inc').write_text(macro)
        for engine in ['reference','candidate']:
            common=(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':ext-src/php_swoole_cxx.cc'],text=True) if engine=='reference' else (work/'ext-src/php_swoole_cxx.cc').read_text())
            table=(common[common.index('static const char *sw_known_strings[]'):common.index('SW_API zend_string **sw_zend_known_strings')] if engine=='reference' else '')
            pieces=[table,'zend_string **sw_zend_known_strings=nullptr;',body(common,'void known_strings_init() {'),body(common,'void known_strings_dtor() {'),body(common,'Callable::~Callable() {')]
            (work/(engine+'-cache.inc')).write_text('\n'.join(pieces))
        cache=work/'cache'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('cache.cc'),archive,'-lpthread','-lm','-o',cache]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete cache/callable fixture compilation failed')
        cache_result=run([cache]);report['passed']=report['passed'] and cache_result.returncode==0
        if not cache_result.returncode:report['cache_observations']=json.loads(cache_result.stdout)
        declarations='static zend_function *fn_swoole_call_array_method=nullptr,*fn_swoole_call_string_method=nullptr,*fn_swoole_call_stream_method=nullptr,*fn_array_push=nullptr,*fn_array_unshift=nullptr,*fn_array_splice=nullptr;\nstatic zif_handler ori_handler_array_push=nullptr,ori_handler_array_unshift=nullptr,ori_handler_array_splice=nullptr;'
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            (work/(engine+'-registration.inc')).write_text(declarations+'\n'+body(content,'void php_swoole_stdext_minit(int module_number) {'))
        registration=work/'registration'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('registration.cc'),archive,'-lpthread','-lm','-o',registration]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete stdext registration fixture compilation failed')
        registration_result=run([registration]);report['passed']=report['passed'] and registration_result.returncode==0
        if not registration_result.returncode:report['registration_observations']=json.loads(registration_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            (work/(engine+'-regex.inc')).write_text(body(content.replace(' /* {{{ */',''),'static void php_do_pcre_match('))
        report['regex_observations']=[]
        for version in [80235,80500]:
            regex=work/('regex-'+str(version))
            command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-DPHP_VERSION_ID='+str(version),'-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('regex.cc'),archive,'-lpthread','-lm','-o',regex]
            command+=sanitizer_flags
            if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
            if run(command).returncode:raise ValueError('Complete PCRE wrapper fixture compilation failed')
            regex_result=run([regex]);report['passed']=report['passed'] and regex_result.returncode==0
            if not regex_result.returncode:report['regex_observations'].append(json.loads(regex_result.stdout))
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            start=content.index('#define SW_CREATE_PHP_FUNCTION_WRAPPER')
            if engine=='candidate':start=content.rfind('#ifdef SWOOLE_RS_PHPHELPERS',0,start)
            end=content.index('PHP_FUNCTION(swoole_parse_str)',start)
            (work/(engine+'-wrappers.inc')).write_text(content[start:end])
        wrappers=work/'wrappers'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('wrappers.cc'),archive,'-lpthread','-lm','-o',wrappers]
        command+=sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete builtin wrapper fixture compilation failed')
        wrappers_result=run([wrappers]);report['passed']=report['passed'] and wrappers_result.returncode==0
        if not wrappers_result.returncode:report['wrappers_observations']=json.loads(wrappers_result.stdout)
        for engine in ['reference','candidate']:
            content=original if engine=='reference' else selected
            (work/(engine+'-predicates.inc')).write_text('\n'.join(body(content,signature) for signature in
                ['PHP_FUNCTION(swoole_str_is_empty) {','PHP_FUNCTION(swoole_array_is_empty) {']))
        predicates=work/'predicates'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('predicates.cc'),archive,'-lpthread','-lm','-o',predicates]+sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Complete empty predicate fixture compilation failed')
        predicate_result=run([predicates]);report['passed']=report['passed'] and predicate_result.returncode==0
        if not predicate_result.returncode:report['predicate_observations']=json.loads(predicate_result.stdout)
        for family,classes in [('facade',['String','CharPtr']),('valuefacade',['KeyValue','Variable']),('iteratorfacade',['ArrayIterator','Array'])]:
            for engine in ['reference','candidate']:
                content=public_header if engine=='reference' else (work/'ext-src/php_swoole_cxx.h').read_text()
                pieces=[]
                for name in classes:
                    start=content.index('class '+name+' {');end=content.index('\n};',start)+3
                    piece=content[start:end]
                    if family=='iteratorfacade':
                        # Only the unused postfix declarator name is omitted in
                        # the model; actual method bodies and production header
                        # remain unchanged, with -Wextra/-Werror still enabled.
                        piece=piece.replace('void operator++(int i)', 'void operator++(int)')
                        report['iterator_fixture_adapter']='Only unused postfix parameter name omitted; types/body unchanged; actual SDK header unchanged.'
                    pieces.append(piece)
                (work/(engine+'-'+family+'.inc')).write_text('\n'.join(pieces))
            facade=work/family
            command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name(family+'.cc'),archive,'-lpthread','-lm','-o',facade]+sanitizer_flags
            if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
            if run(command).returncode:raise ValueError('Complete String/CharPtr lifecycle fixture compilation failed')
            facade_result=run([facade]);report['passed']=report['passed'] and facade_result.returncode==0
            if not facade_result.returncode:report[family+'_observations']=json.loads(facade_result.stdout)
        for engine in ['reference','candidate']:
            content=public_header if engine=='reference' else (work/'ext-src/php_swoole_cxx.h').read_text()
            start=content.index('class Callable {');end=content.index('\n};',start)+3
            piece='namespace zend {\n'+content[start:end]+'\nCallable::Callable(zval *value) { construct(&zfn,&fcc,&fn_name,value); }\nCallable::~Callable() { destroy(&zfn,fn_name); }\n}\n'
            piece+='\n'.join(body(content,signature) for signature in ['static inline zend::Callable *sw_callable_create(zval *zfn) {','static inline zend::Callable *sw_callable_create_ex('])
            (work/(engine+'-callablefacade.inc')).write_text(piece)
        callablefacade=work/'callablefacade'
        command=['c++','-std=c++17','-O2','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(ROOT/'native/phphelpers'),Path(__file__).with_name('callablefacade.cc'),archive,'-lpthread','-lm','-o',callablefacade]+sanitizer_flags
        if sys.platform.startswith('linux'):command+=['-ldl','-lrt','-lutil']
        if run(command).returncode:raise ValueError('Inline Callable/factory fixture compilation failed')
        callable_result=run([callablefacade]);report['passed']=report['passed'] and callable_result.returncode==0
        if not callable_result.returncode:report['callablefacade_observations']=json.loads(callable_result.stdout)
    except Exception as error:
        report['passed']=False;report['error']=str(error)
        if isinstance(error,subprocess.CalledProcessError):report['error_stderr']=str(error.stderr)
    checkpoint();print(json.dumps({k:report.get(k) for k in ['passed','error','work']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
