#!/usr/bin/env python3
"""TableV2 custody and original/selected complete table TU release syntax; not runtime or configured SDK proof."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated
from tools.build_hybrid import hybrid_tree
from tools.build_upstream import COMMIT as PIN
FIXTURE = '''#include "swoole_rs_memory_table_v2.h"
#include <type_traits>
#include <utility>
template <class...> using Void = void;
template <class T, class = void> struct HasColumns : std::false_type {};
template <class T> struct HasColumns<T, Void<decltype(std::declval<T>().column_list)>> : std::true_type {};
template <class T, class = void> struct HasCore : std::false_type {};
template <class T> struct HasCore<T, Void<decltype(std::declval<T>().core_)>> : std::true_type {};
static_assert(!HasColumns<swoole::TableV2>::value && !HasCore<swoole::TableV2>::value, "no public vector/core escape");
static_assert(!std::is_convertible<swoole::TableV2*,swoole::Table*>::value, "no legacy object conversion");
static_assert(!std::is_default_constructible<swoole::TableV2>::value && !std::is_copy_constructible<swoole::TableV2>::value, "factory ownership");
static_assert(!std::is_destructible<swoole::TableV2>::value, "explicit destroy API");
using RecordView = swoole::TableV2::Column;
static_assert(!std::is_pointer<decltype(std::declval<swoole::TableV2>().get_column(std::string()))>::value, "copied descriptor, not native column pointer");
static_assert(std::is_same<decltype(std::declval<swoole::TableV2>().get_column(std::string())), RecordView>::value, "typed record value");
static_assert(std::is_same<decltype(std::declval<swoole::TableV2::ColumnCursor>().next(std::declval<RecordView&>())), bool>::value, "copy-out cursor");
static_assert(std::is_same<decltype(std::declval<RecordView>().copy_name(nullptr, 0)), bool>::value, "native owned name copy");
static_assert(std::is_same<decltype(std::declval<swoole::Table>().column_list), std::vector<swoole::TableColumn*>*>::value, "legacy type unchanged");
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True, help='Rust archive of the hybrid build under test')
    parser.add_argument('--cxx', default='c++')
    parser.add_argument('--upstream-unused-parameter-policy', action='store_true', help='Explicit pinned maintainer unused-parameter suppression; strict remains separate')
    parser.add_argument('--fixed-pool', action='store_true', help='Also compile unchanged original and selected complete FixedPool source; no runtime')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'passed': False, 'scope': __doc__, 'upstream_commit': PIN, 'commands': [],
              'unused_parameter_suppression': args.upstream_unused_parameter_policy}
    try:
        if args.fixed_pool:
            report['scope'] += ' Optional original/selected complete FixedPool TUs included; no runtime.'
        # The selected side is the hybrid build's fully patched tree; the original is the pin.
        hybrid_source, hybrid_flags = hybrid_tree(args.archive)
        report['hybrid_tree'] = str(hybrid_source)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        archive = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/memory/table.cc', *(['src/memory/fixed_pool.cc'] if args.fixed_pool else [])], timeout=15)
        with tempfile.TemporaryDirectory(prefix='swr-table-v2-compat-') as temporary:
            tree = Path(temporary)
            control = tree / 'original'
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                for member in bundle:
                    if member.isfile():
                        original = control / member.name
                        original.parent.mkdir(parents=True, exist_ok=True)
                        original.write_bytes(bundle.extractfile(member).read())
            report['hash_configuration'] = {
                'selected': 'SW_TABLE_USE_PHP_HASH is unconditionally defined by pinned swoole_table.h',
                'austin_branch': 'Unqualified; command-line undef does not override the pinned header define. No header variant silently invented.',
                'custom_callbacks': 'Runtime callback corpus is separate, not qualified by compiler-only checks',
            }
            fixture = tree / 'facade.cc'
            fixture.write_text(FIXTURE)
            pinned = ['-I' + str(control / 'include')]
            units = [
                ('typed-header', fixture, hybrid_flags),
                ('selected-table', hybrid_source / 'src/memory/table.cc', hybrid_flags),
                ('original-table', control / 'src/memory/table.cc', pinned),
            ]
            if args.fixed_pool:
                units.extend([
                    ('selected-fixed-pool', hybrid_source / 'src/memory/fixed_pool.cc', hybrid_flags),
                    ('original-fixed-pool', control / 'src/memory/fixed_pool.cc', pinned),
                ])
            for standard in ['c++14', 'c++17', 'c++20']:
                for label, unit, headers in units:
                    command = [*shlex.split(args.cxx), '-std=' + standard, '-DNDEBUG',
                               '-Wall', '-Wextra', '-Werror',
                               *(['-Wno-unused-parameter'] if args.upstream_unused_parameter_policy else []), '-fsyntax-only',
                               *headers, *flags, str(unit)]
                    result = run_isolated(command, timeout=30)
                    report['commands'].append({'case': label, 'standard': standard, 'argv': command,
                                               'returncode': result.returncode,
                                               'stdout': result.stdout, 'stderr': result.stderr})
            report['passed'] = all(c['returncode'] == 0 and not c['stderr'] for c in report['commands'])
    except Exception as error:
        report['error'] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['passed', 'error']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
