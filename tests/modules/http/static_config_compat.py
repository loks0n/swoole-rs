#!/usr/bin/env python3
"""Static configuration SDK source controls; ON explicitly requires a rebuilt SDK."""
import argparse
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, apply_http_patch
from rewrite_store_compat import server_layout
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_hybrid import apply_patch_verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-static-config-compat.json')
    args = parser.parse_args()
    report = {'passed': False, 'full_gate_passed': False, 'pin': PIN, 'checks': [],
              'scope': 'Pinned unconfigured actual Server SDK/layout and whole static/master source syntax. ON changes Server public SDK/layout; no configured production/runtime/external ABI qualification.',
              'on_public_compatibility': 'UNFINISHED: legacy config fields and root-reference accessor unavailable; selected SDK rebuild required'}
    def checked(command, name):
        row = {'name': name, 'command': command, 'free_bytes': min(shutil.disk_usage(p).free for p in [ROOT, Path.cwd(), Path(tempfile.gettempdir())]), 'guard_bytes': 4*1024**3}
        report['checks'].append(row)
        if row['free_bytes'] < row['guard_bytes']:
            row['blocked'] = 'unchanged disk guard'; return None
        value = run_isolated(command, timeout=60)
        row.update(returncode=value.returncode, stdout=value.stdout, stderr=value.stderr)
        return value if value.returncode == 0 else None
    with tempfile.TemporaryDirectory(prefix='swr-static-config-sdk-') as temporary:
        tree = Path(temporary); original = tree/'original'; selected = tree/'selected'
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/server/static_handler.cc', 'src/server/master.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = original/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        shutil.copytree(original, selected)
        for name in ['0002-static-ranges.patch', '0003-static-inline.patch']:
            apply_http_patch(selected, ROOT/'migration/patches/http'/name, report)
        manifest = ROOT/'migration/patches/integration/manifest.json'
        for item in json.loads(manifest.read_text())['patches']:
            if set(item['upstream_paths']) <= {'include/swoole_server.h', 'src/server/master.cc'}:
                report.setdefault('shared_patch_application', []).append(apply_patch_verified(selected, manifest.parent/item['path'], item['upstream_paths'], item['sha256']))
        header = (selected/'include/swoole_server.h').read_text()
        master = (selected/'src/server/master.cc').read_text()
        if 'http_server::StaticConfig static_config_' not in header or 'static_files().root_begin' not in master:
            report['blocked'] = 'Concrete paired shared Server/master static configuration source absent'
            write_report(args.output, report); return 1
        source = tree/'layout.cc'
        source.write_text('''#include "swoole_static_handler.h"
#include <type_traits>
#include <utility>
using T=swoole::Server;
static_assert(!std::is_copy_constructible<T>::value && !std::is_copy_assignable<T>::value,"existing noncopyable Server");
static_assert(!std::is_move_constructible<T>::value && !std::is_move_assignable<T>::value,"existing nonmovable Server");
#if defined(SWOOLE_RS_HTTP_STATIC_CONFIG) && SWOOLE_RS_HTTP_STATIC_CONFIG
static_assert(std::is_same<decltype(std::declval<T&>().static_files()),swoole::http_server::StaticConfig&>::value,"actual typed owner");
static_assert(sizeof(swoole::http_server::StaticConfig)==sizeof(void*),"sole opaque owner, no Native config mirror");
#else
static_assert(std::is_same<decltype(std::declval<T&>().locations),std::shared_ptr<std::unordered_set<std::string>>>::value,"original location field");
static_assert(std::is_same<decltype(std::declval<T&>().http_index_files),std::shared_ptr<std::vector<std::string>>>::value,"original index field");
static_assert(std::is_same<decltype(std::declval<T&>().get_document_root()),const std::string&>::value,"original root reference");
#endif
static_assert(sizeof(T)>0,"complete actual layout");
''')
        flags = ['-DSWOOLE_RS_HTTP=1', '-fsyntax-only', '-I'+str(ROOT/'native/http')]
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        for standard in ['c++14', 'c++17']:
            baseline = None
            for mode, world, macro in [('original', original, []), ('omitted', selected, []), ('off', selected, ['-DSWOOLE_RS_HTTP_STATIC_CONFIG=0']), ('on', selected, ['-DSWOOLE_RS_HTTP_STATIC_CONFIG=1'])]:
                command = ['c++', '-std='+standard, *flags, *macro, '-I'+str(world/'include'), '-Xclang', '-fdump-record-layouts', str(source)]
                value = checked(command, standard+'-'+mode+'-layout')
                if value is None: write_report(args.output, report); return 1
                layout = server_layout(value.stdout+'\n'+value.stderr)
                report['checks'][-1]['server_layout'] = layout
                if baseline is None: baseline = layout
                elif mode != 'on' and layout != baseline:
                    report['failed'] = 'Omitted/OFF Server layout changed'; write_report(args.output, report); return 1
                elif mode == 'on':
                    report['checks'][-1]['layout_matches_original'] = layout == baseline
                    if layout == baseline:
                        report['failed'] = 'Expected explicit selected SDK layout change absent'; write_report(args.output, report); return 1
                if world == selected:
                    for rel in ['src/server/static_handler.cc', 'src/server/master.cc']:
                        if checked(['c++', '-std='+standard, *flags, *macro, '-I'+str(world/'include'), str(world/rel)], standard+'-'+mode+'-'+rel) is None:
                            write_report(args.output, report); return 1
        report['passed'] = True; write_report(args.output, report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
