#!/usr/bin/env python3
"""Exact read/grow loop bodies with scalar IO/reserve adapters; no host fixtures/fault probe."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
PIN = "8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path, help='Pinned Git checkout with host config.h')
    args = parser.parse_args()
    out = ROOT / 'target/read-content' / uuid.uuid4().hex
    out.mkdir(parents=True)
    report = dict(passed=False, platform=sys.platform, pin=PIN, commands=[], output=str(out),
                  scope='Exact File::read_content + pinned String::grow bodies with scalar read/reserve adapters; no actual native String/File/DSO/PHP/original/platform/sanitizer/performance claim')
    inputs = [ROOT / f for f in ['crates/ossupport/src/lib.rs', 'crates/ossupport/src/read_content.rs', 'crates/ossupport/src/file_line.rs', 'crates/ossupport/src/file_content.rs', 'crates/ossupport/src/random_bytes.rs',
              'crates/ossupport/src/file_io.rs', 'crates/ossupport/src/sendfile_fallback.rs', 'crates/ossupport/Cargo.toml', 'Cargo.toml', 'Cargo.lock',
              'native/ossupport/swoole_rs_ossupport.h', 'migration/patches/ossupport/0001-os-policy.patch',
              'migration/patches/ossupport/manifest.json', 'native/ossupport/contract.md', 'tests/modules/ossupport/read_content.cpp',
              'tests/modules/ossupport/read_content.py']]
    sdk = [args.source / f for f in ['config.h', 'include/swoole.h', 'include/swoole_socket.h', 'include/swoole_string.h', 'include/swoole_config.h']]
    report['sdk_before'] = {str(p): sha(p) for p in sdk}
    report['before'] = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    for p in inputs:
        copy = out / 'inputs' / p.relative_to(ROOT)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, copy)
    def run(argv):
        assert shutil.disk_usage(out).free >= 4*1024**3 + 128*1024**2, '4GiB guard plus 128MiB stop margin'
        n = len(report['commands'])
        r = subprocess.run([str(x) for x in argv], cwd=ROOT, capture_output=True, timeout=90)
        log = out / str(n)
        log.with_suffix('.stdout').write_bytes(r.stdout)
        log.with_suffix('.stderr').write_bytes(r.stderr)
        report['commands'].append(dict(argv=[str(x) for x in argv], exit=r.returncode,
            stdout=str(log.with_suffix('.stdout')), stderr=str(log.with_suffix('.stderr'))))
        if r.returncode:
            raise RuntimeError('command failed: ' + str(argv))
        return r.stdout
    try:
        targets = json.loads((ROOT / 'migration/patches/ossupport/manifest.json').read_text())['patches'][0]
        patch = ROOT / 'migration/patches/ossupport' / targets['path']
        assert sha(patch) == targets['sha256']
        for name in targets['upstream_paths']:
            dest = out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(run(['git', '-C', args.source, 'show', PIN + ':' + name]))
        original = run(['git', '-C', args.source, 'show', PIN + ':src/os/file.cc']).decode()
        run(['patch', '--fuzz=0', '-p1', '-d', out, '-i', patch])
        selected = (out / 'src/os/file.cc').read_text()
        for name, text in [('original', original), ('selected', selected)]:
            start = text.index('std::shared_ptr<String> File::read_content() const')
            body = text[start:text.index('\n}', start)+2]+'\n'
            (out / (name + '.inc')).write_text(body)
        grow = run(['git', '-C', args.source, 'show', PIN + ':src/core/string.cc']).decode()
        start = grow.index('void String::grow(')
        (out/'grow.inc').write_text(grow[start:grow.index('\n}',start)+2]+'\n')
        assert 'ssize_t n = 0;\n    auto data = std::make_shared<String>(SW_BUFFER_SIZE_STD);' in selected
        assert selected.count('n = read(data->str + data->length, data->size - data->length);')==1
        assert selected.count('data->grow((size_t) n);')==1
        run(['cargo', 'test', '--locked', '--offline', '-p', 'swoole-rs-ossupport', '--target-dir', out/'cargo', 'read_content::tests'])
        run(['cargo', 'rustc', '--locked', '--offline', '--release', '-p', 'swoole-rs-ossupport',
             '--target-dir', out/'cargo', '--', '--crate-type', 'staticlib'])
        archives = list((out/'cargo/release/deps').glob('libswoole_rs_ossupport*.a'))
        assert len(archives) == 1, archives
        archive = archives[0]
        report['archive'] = str(archive)
        report['archive_before'] = sha(archive)
        ccache = shutil.which('ccache')
        compiler = [ccache, 'c++'] if ccache else ['c++']
        run([*compiler, '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', '-DSWOOLE_RS_OSSUPPORT', '-I'+str(ROOT/'native/ossupport'),
             '-I'+str(out), ROOT/'tests/modules/ossupport/read_content.cpp', archive,
             *(['-ldl', '-lpthread', '-lm'] if sys.platform == 'linux' else []), '-o', out/'read-content'])
        result = run([out/'read-content']).decode()
        assert result.endswith('PASS\t1568\n'), result[-200:]
        report['controlled_cases'] = int(result.splitlines()[-1].split('\t')[1])
        run([*compiler, '-std=c++14', '-fsyntax-only', '-DHAVE_CONFIG_H', '-DSWOOLE_RS_OSSUPPORT',
             '-I'+str(args.source), '-I'+str(args.source/'include'), '-I'+str(ROOT/'native/ossupport'),
             *(['-I/opt/homebrew/opt/openssl@3/include'] if sys.platform == 'darwin' else []), out/'src/os/file.cc'])
        report['whole_file_syntax'] = 'passed; unrelated method identity checked separately'
        symbols = run(['nm', '-g', out/'read-content']).decode()
        assembly = run(['otool', '-tvV', out/'read-content'] if sys.platform == 'darwin' else ['objdump', '-d', '-C', out/'read-content']).decode()
        assert re.search(r'\bT\s+_?swr_v1_os_read_content_next\b', symbols)
        if sys.platform == 'darwin':
            label = next(line for line in assembly.splitlines() if 'ZNK8selected4File12read_content' in line and line.endswith(':'))
        else:
            label = next(line for line in assembly.splitlines() if '<selected::File::read_content(' in line and line.endswith(':'))
        body = re.split(r'\n(?:[^\n\t]+:|[0-9a-f]+ <[^\n]+>:)\n', assembly.split(label, 1)[1], maxsplit=1)[0]
        calls = [line.strip() for line in body.splitlines()
                 if 'swr_v1_os_read_content_next' in line and re.search(r'\b(?:bl|b|callq?)\s', line)]
        assert calls
        report['actual_selected_calls'] = calls
        report['archive_after'] = sha(archive)
        report['sdk_after'] = {str(p): sha(p) for p in sdk}
        assert report['sdk_before'] == report['sdk_after']
        report['after'] = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
        assert report['before'] == report['after']
        assert report['archive_before'] == report['archive_after']
        report['passed'] = True
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(out/'report.json')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
