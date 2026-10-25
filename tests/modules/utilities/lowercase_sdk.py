#!/usr/bin/env python3
"""Compile unchanged HTTP Response consumers with original/selected utility headers."""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated, write_report
from overlay import apply_owned

from tools.build_upstream import COMMIT as PIN
CALLER = 'ext-src/swoole_http_response.cc'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--sdk-export', type=Path, required=True, help='Completed native export.json and config.h')
    parser.add_argument('--php-config', default='php-config')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve().parent / ('lowercase-sdk-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, work=str(work), pin=PIN, commands=[], scope=__doc__)
    try:
        export = json.loads(args.sdk_export.read_text())
        config = args.sdk_export.with_name('config.h')
        if sha(config) != export['files']['config.h']['sha256']:
            raise ValueError('SDK config differs from completed native export')
        names = subprocess.check_output(['git', '-C', str(args.source), 'ls-tree', '-r', '--name-only', PIN], text=True).splitlines()
        names = [name for name in names if Path(name).suffix in ['.h', '.hpp', '.inc'] or name == CALLER]
        packed = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, '--', *names])
        native = work / 'native'
        with tarfile.open(fileobj=io.BytesIO(packed)) as bundle:
            for member in bundle:
                if not member.isfile():
                    continue
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Invalid pinned path')
                target = native / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.extractfile(member).read())
        shutil.copy2(config, native / 'config.h')
        if re.search(r'^\s*#define\s+SWOOLE_RS_UTILITIES\b', config.read_text(), re.M):
            raise ValueError('Require native SDK configuration')
        selected = work / 'selected'
        patch = ROOT / 'migration/patches/utilities/0003-inline-bytes.patch'
        shutil.copytree(native, selected)
        report['overlay_application'] = apply_owned(selected, patch)
        shutil.copy2(ROOT / 'native/utilities/swoole_rs_utilities.h', selected / 'swoole_rs_utilities.h')
        if (selected / CALLER).read_bytes() != (native / CALLER).read_bytes():
            raise ValueError('Protected consumer changed')
        includes = shlex.split(subprocess.check_output([args.php_config, '--includes'], text=True))
        report['php_sdk'] = subprocess.check_output([args.php_config, '--version'], text=True).strip()
        packages = ['openssl', 'libpcre2-8']
        for macro, package in [('SW_USE_CURL', 'libcurl'), ('SW_USE_PGSQL', 'libpq')]:
            if re.search(r'^\s*#define\s+' + macro + r'\b', config.read_text(), re.M):
                packages.append(package)
        report['pkg_config_packages'] = packages
        flags = run_isolated(['pkg-config', '--cflags', *packages], timeout=15)
        report['pkg_config'] = dict(exit=flags.returncode, stdout=flags.stdout, stderr=flags.stderr)
        if flags.returncode:
            raise ValueError('SDK pkg-config prerequisites unavailable')
        for engine, tree in [('native', native), ('selected', selected)]:
            for mode in ['signed', 'unsigned']:
                obj, dep = work / (engine + '-' + mode + '.o'), work / (engine + '-' + mode + '.d')
                command = ['c++', '-std=c++14', '-O2', '-c', '-f' + mode + '-char', '-DENABLE_PHP_SWOOLE', '-DHAVE_CONFIG_H',
                           *['-I' + str(tree / path) for path in ['', 'include', 'ext-src', 'thirdparty', 'thirdparty/llhttp']],
                           *includes, *shlex.split(flags.stdout), *(['-DSWOOLE_RS_UTILITIES'] if engine == 'selected' else []),
                           '-MD', '-MF', str(dep), str(tree / CALLER), '-o', str(obj)]
                result = run_isolated(command, timeout=120)
                row = dict(engine=engine, char=mode, command=command, exit=result.returncode,
                           stdout=result.stdout, stderr=result.stderr)
                report['commands'].append(row)
                if result.returncode == 0:
                    symbols = run_isolated(['nm', '-u', str(obj)], timeout=15)
                    row['imports'] = dict(exit=symbols.returncode, stdout=symbols.stdout, stderr=symbols.stderr)
                    row['expected_lowercase_import'] = (symbols.returncode == 0 and
                        ('swr_v1_utils_lowercase' in symbols.stdout) == (engine == 'selected'))
                write_report(args.output, report)
        report['passed'] = len(report['commands']) == 4 and all(row['exit'] == 0 and row.get('expected_lowercase_import') for row in report['commands'])
    except Exception as error:
        report['passed'], report['error'] = False, str(error)
    write_report(args.output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
