#!/usr/bin/env python3
"""Exact stack marker fragments on ordinary byte buffers; no context execution."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
from ordered_gate import block, ROOT, PIN
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def marker_region(source):
    start = source.index('#ifdef SW_CONTEXT_DETECT_STACK_USAGE', source.index('Context::Context('))
    lines = source[start:].splitlines(True)
    depth = 0
    for end, line in enumerate(lines):
        if line.startswith(('#if ', '#ifdef ', '#ifndef ')):
            depth += 1
        elif line.startswith('#endif'):
            depth -= 1
            if depth == 0:
                return ''.join(lines[:end + 1])
    raise ValueError('Unterminated marker preprocessor region')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--sanitize', action='store_true')
    p.add_argument('--rust-instrumented', action='store_true', help='Verify Rust ASan archive imports; Linux mixed profile only')
    a = p.parse_args()
    if a.rust_instrumented and sys.platform != 'linux':
        p.error('Mixed Rust/native instrumentation is qualified separately on Linux only')
    a.report = a.report.resolve()
    if a.report.exists():
        p.error('Choose a unique new receipt')
    a.report.parent.mkdir(parents=True, exist_ok=True)
    work = a.report.parent / ('context-markers-' + uuid.uuid4().hex)
    work.mkdir()
    manifest = ROOT / 'migration/patches/coroutine/manifest.json'
    entries = json.loads(manifest.read_text())['patches']
    bound = [a.archive.resolve(), Path(__file__), Path(__file__).with_suffix('.cc'), manifest,
             ROOT / 'native/coroutine/swoole_rs_coroutine.h',
             *sorted((ROOT / 'crates/coroutine/src').glob('*.rs')),
             *[manifest.parent / entry['path'] for entry in entries]]
    identities = {str(path): digest(path) for path in bound}
    report = dict(passed=False, full_gate_passed=False, pin=PIN, scope=__doc__,
                  inputs_sha256=identities, native_sanitized=a.sanitize, rust_instrumented=a.rust_instrumented,
                  rust_std_instrumented=False,
                  archive_source_attested_here=False, commands=[], results=[], work=str(work))
    try:
        if a.rust_instrumented:
            symbols = subprocess.check_output(['nm', '-u', str(a.archive)], text=True, stderr=subprocess.DEVNULL)
            report['rust_asan_report_imports'] = sorted(set(line.strip() for line in symbols.splitlines() if '__asan_report_' in line))
            if not report['rust_asan_report_imports']:
                raise ValueError('Supplied archive has no actual Rust ASan report imports')
        originals = {}
        tree = work / 'patched-source'
        for entry in entries:
            for name in entry['upstream_paths']:
                if name not in originals:
                    text = subprocess.check_output(['git', '-C', str(a.source), 'show', PIN + ':' + name], text=True)
                    originals[name] = text
                    target = tree / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text)
        report['patch_proofs'] = [apply_patch_verified(tree, manifest.parent / entry['path'],
                                  entry['upstream_paths'], entry['sha256']) for entry in entries]
        name = 'src/coroutine/context.cc'
        for label, source in [('native', originals[name]), ('selected', (tree / name).read_text())]:
            folder = work / label
            folder.mkdir()
            definitions = '\n'.join(line for line in source.splitlines()
                                    if line.startswith(('#define MAGIC_STRING ', '#define START_OFFSET ')))
            if label == 'selected' and 'SWR_CTX_STACK_MARK' in source:
                # Same existing initialized-byte assertions, projected onto the
                # intentionally changed cells. This is an inert global record,
                # not swoole::coroutine::Context or its resource constructor.
                body = definitions + '''
struct Context {
    swr_v1_context_stack_cell stack_; swr_v1_context_extent stack_size_;
    Context(char *pointer, size_t size) : stack_{pointer}, stack_size_(swr_v1_context_extent_new(size)) {}
    ssize_t get_stack_usage();
};
void initialize(char *pointer, size_t stack_size) {
    swr_v1_context_stack_cell stack_{pointer};
    swr_v1_context_extent stack_size_ = swr_v1_context_extent_new(stack_size);
'''
            else:
                body = definitions + '\nstruct Context { char *stack_; size_t stack_size_; ssize_t get_stack_usage(); };\n'
                body += 'void initialize(char *stack_, size_t stack_size) { void *sp=stack_+stack_size; (void)sp;\n'
            body += marker_region(source) + '}\n' + block(source, 'ssize_t Context::get_stack_usage()')
            (folder / 'stack.inc').write_text(body)
            binary = folder / 'markers'
            command = ['c++', '-std=c++14', '-O1', '-g', '-UNDEBUG', '-DSW_CONTEXT_DETECT_STACK_USAGE',
                       '-I' + str(folder), '-I' + str(ROOT / 'native/coroutine'),
                       *(['-DSWOOLE_RS_COROUTINE'] if label == 'selected' else []),
                       str(Path(__file__).with_suffix('.cc')), *([str(a.archive.resolve())] if label == 'selected' else []),
                       '-lpthread', *(['-ldl', '-lm'] if sys.platform.startswith('linux') else []), '-o', str(binary)]
            if a.sanitize:
                command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
            for stage, cmd in [('compile', command), ('execute', [str(binary)])]:
                require_build_space(work)
                r = run_isolated(cmd, cwd=folder, timeout=90)
                report['commands'].append(dict(engine=label, stage=stage, command=cmd,
                                                exit=r.returncode, stdout=r.stdout, stderr=r.stderr))
                write_report(a.report, report)
                if r.returncode or r.stderr:
                    raise ValueError(label + ' ' + stage + ' failed or warned')
            report['results'].append(dict(engine=label, summary=json.loads(r.stdout)))
        if report['results'][0]['summary'] != report['results'][1]['summary']:
            raise ValueError('Original and selected marker observations differ')
        if any(digest(path) != identity for path, identity in identities.items()):
            raise ValueError('Input changed during check')
        report.update(passed=True, inputs_before_after_equal=True)
    except Exception as error:
        report['error'] = str(error)
    write_report(a.report, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'results']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
