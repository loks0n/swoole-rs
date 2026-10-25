#!/usr/bin/env python3
"""Matched pinned/selected primitive context models; no real Zend, contexts or callbacks."""
import argparse
import json
import sys
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report
from make_patches import body, header_selected, coroutine_selected
from gate import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve().parent / ('phpcoroutines-metadata-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, commands=[], work=str(work), archive_sha256=sha(args.archive),
                  measurement_performed=False, actual_php_executed=False,
                  limits=['Only primitive ordinary model state with copied Native error/clock facts; real Zend/VM/observer/context lifetime absent.',
                          'Native ASan/UBSan instruments C++ consumer only; Rust archive is optimized and uninstrumented.',
                          'Pinned original inventories, ZTS/configuration union, fault/IPC/stopped profiles and performance unqualified.'])
    try:
        h = (args.source / 'ext-src/php_swoole_coroutine.h').read_text()
        cc = (args.source / 'ext-src/swoole_coroutine.cc').read_text()
        hs, cs = header_selected(h), coroutine_selected(cc)
        report['inputs_sha256'] = {str(p): sha(p) for p in [Path(__file__), ROOT/'native/phpcoroutines/swoole_rs_phpcoroutines.h', ROOT/'tests/modules/phpcoroutines/context_metadata.cc']}
        template = (ROOT/'tests/modules/phpcoroutines/context_metadata.cc').read_text()
        for engine, header, source in [('native', h, cc), ('selected', hs, cs)]:
            fragments = []
            for signature in ('static inline bool is_schedulable(PHPContext *ctx) {', 'static inline bool enable_scheduler() {', 'static inline bool disable_scheduler() {'):
                fragments.append(signature + body(header, signature) + '}')
            fragments += ['static PHPContext *get_context() { return current; }']
            text = '\n'.join(fragments)
            template = template.replace('/* ' + engine + '_methods */', text)
            helpers = []
            if engine == 'selected':
                signature = 'static inline swr_phpcoroutines_context_cells php_coroutine_metadata_cells(PHPContext *ctx) {'
                helpers.append(signature + body(header, signature) + '}')
            for signature in ('static int coro_begin_silence_handler(zend_execute_data *execute_data) {', 'static int coro_end_silence_handler(zend_execute_data *execute_data) {'):
                helpers.append(signature + body(source, signature) + '}')
            for name in ('save', 'restore'):
                signature = 'inline void PHPCoroutine::' + name + '_vm_stack(PHPContext *ctx) {'
                content = body(source, signature)
                if engine == 'native':
                    signature = 'if (UNEXPECTED(ctx->in_silence)) {'
                    content = signature + body(content, signature) + '}'
                else:
                    from metadata_bodies import silence
                    content = silence('SAVE' if name == 'save' else 'RESTORE')
                helpers.append('static void ' + name + '_mask(PHPContext *ctx) {\n' + content + '\n}')
            template = template.replace('/* ' + engine + '_helpers */', '\n'.join(helpers))
        source = work / 'model.cc'
        source.write_text(template)
        for profile, flags in [('normal', []), ('native-asan-ubsan', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
            binary = work / profile
            commands = [['c++', '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-DSWOOLE_RS_PHPCOROUTINES',
                         '-I'+str(ROOT/'native/phpcoroutines'), '-I'+str(ROOT/'native/include'), str(source), str(args.archive), '-lpthread', '-ldl', '-lm', *flags, '-o', str(binary)], [str(binary)]]
            for command in commands:
                require_build_space(ROOT)
                result = run_isolated(command, timeout=120)
                report['commands'].append(dict(profile=profile, command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
                write_report(args.output, report)
                if result.returncode:
                    raise ValueError('Primitive matched model failed; initial outcome retained')
            if result.stdout != 'CONTEXT_METADATA_MODELS_OK\n':
                raise ValueError('Unexpected primitive model result')
            report[profile] = dict(result=result.stdout)
        if sha(args.archive) != report['archive_sha256']:
            raise ValueError('Archive changed during model qualification')
        if any(sha(p) != digest for p, digest in report['inputs_sha256'].items()):
            raise ValueError('Model inputs changed')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({k: report.get(k) for k in ('passed', 'error', 'work')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
