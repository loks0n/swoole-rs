#!/usr/bin/env python3
"""Ordinary join identity/refcount metadata controls; no PHP, Native join or callback execution."""
import argparse
import json
from pathlib import Path
import sys
import uuid
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report
from overlay import body, coroutine_selected
from join_bodies import OWNER, SIGNATURE
from gate import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve().parent / ('phpcoroutines-join-metadata-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, work=str(work), commands=[], archive_sha256=sha(args.archive),
                  measurement_performed=False, actual_php_executed=False, Native_callbacks_executed=0,
                  limits=['Only inert identity records/containers and Native capture reference copy/drop operations; not actual PHPContext, join/defer/yield/resume/retirement or Zend effects.',
                          'Native ASan/UBSan instruments the C++ consumer only, not the optimized Rust archive.',
                          'Opaque pointer-order controls qualify these supported compiler/ABI observations, not other architectures/configuration union.',
                          'No stopped/fault/allocation-failure/lifetime/bailout/ZTS probes, original inventories or performance measurement.'])
    try:
        pin = args.source / 'ext-src/swoole_coroutine.cc'
        source = pin.read_text()
        selected = coroutine_selected(source)
        before, after = body(source, SIGNATURE), body(selected, SIGNATURE)
        if '#else' + before + '#endif\n' not in after or OWNER not in selected:
            raise ValueError('Selected Native owner/caller or exact fallback missing')
        report['inputs_sha256'] = {str(p): sha(p) for p in [Path(__file__), ROOT/'tests/modules/phpcoroutines/join_metadata.cc', ROOT/'tests/modules/phpcoroutines/join_bodies.py', ROOT/'native/phpcoroutines/swoole_rs_phpcoroutines.h']}
        text = (ROOT/'tests/modules/phpcoroutines/join_metadata.cc').read_text().replace('/* join_owner */', OWNER)
        model = work / 'model.cc'; model.write_text(text)
        for profile, flags in [('normal', []), ('native-asan-ubsan', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
            binary = work / profile
            command = ['c++', '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror',
                       '-I'+str(ROOT/'native/include'), '-I'+str(ROOT/'native/phpcoroutines'), str(model), str(args.archive),
                       '-lpthread', '-ldl', '-lm', *flags, '-o', str(binary)]
            for cmd in [command, [str(binary)]]:
                require_build_space(ROOT)
                result = run_isolated(cmd, timeout=120)
                report['commands'].append(dict(profile=profile, command=cmd, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
                write_report(args.output, report)
                if result.returncode:
                    raise ValueError('Ordinary join metadata check failed; initial outcome retained')
            if not result.stdout.startswith('JOIN_METADATA_OK identities=128 ') or not result.stdout.endswith('threads=8 copies=4096 callbacks=0\n'):
                raise ValueError('Unexpected metadata control observations')
            report[profile] = dict(output=result.stdout)
        if sha(args.archive) != report['archive_sha256'] or any(sha(p)!=digest for p,digest in report['inputs_sha256'].items()):
            raise ValueError('Archive or model inputs changed during qualification')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({key:report.get(key) for key in ('passed','error','work')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
