#!/usr/bin/env python3
"""Build a real sockets-enabled variant using the shared builder unchanged.

The shared CLI has no optional-feature argument. This test-only entry point
adds the same configure flag to both its fingerprint and actual configure call.
No production source, probe, macro guard or shared builder is patched.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools import build_hybrid, build_upstream
from tools.harness import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args, forwarded = parser.parse_known_args()
    # Only the two explicit matched configurations belong to this witness.
    if forwarded not in [['--backend', 'upstream', '--dev', '--jobs', '2'],
                         ['--module', 'wrappers', '--dev', '--jobs', '2']]:
        parser.error('Pass --backend upstream --dev --jobs 2 or --module wrappers --dev --jobs 2')
    original = build_upstream.extension_configuration

    def configuration(options, extra=()):
        return original(options, (*extra, '--enable-sockets'))

    build_upstream.extension_configuration = configuration
    build_hybrid.extension_configuration = configuration
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': __doc__,
              'arguments': forwarded, 'passed': False}
    try:
        sys.argv = [str(ROOT / 'tools/build_hybrid.py'), *forwarded]
        result = build_hybrid.main()
        if result:
            raise RuntimeError('Shared builder returned ' + str(result))
        name = 'dev-upstream' if '--backend' in forwarded else 'dev-rust-wrappers'
        manifest = json.loads((ROOT / 'target/hybrid' / name / 'build-manifest.json').read_text())
        if '--enable-sockets' not in manifest['configure']:
            raise RuntimeError('Actual configure lacks sockets integration')
        config = Path(manifest['extension']).parents[1] / 'config.h'
        if '#define SW_SOCKETS 1' not in config.read_text():
            raise RuntimeError('Sockets integration was not configured')
        report.update(build_manifest=manifest, passed=True)
    except Exception as error:
        report['error'] = str(error)
        report['traceback'] = traceback.format_exc()
    finally:
        build_upstream.extension_configuration = original
        build_hybrid.extension_configuration = original
    write_report(args.output, report)
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
