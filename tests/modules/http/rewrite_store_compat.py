#!/usr/bin/env python3
"""Full unconfigured Server SDK/layout and rewrite-store real-TU capability controls."""
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
from gate import PIN, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_hybrid import apply_patch_verified


def record_layout(output, name, normalized):
    """Keep direct member offsets/types and complete geometry of one Clang record."""
    for block in output.split('*** Dumping AST Record Layout'):
        lines = block.splitlines()
        if not any(re.search(r'\| (?:class|struct) '+re.escape(name)+r'$', line) for line in lines):
            continue
        fields = []
        for line in lines:
            match = re.match(r'^\s*(\d+)\s*\|   (\S.*)$', line)
            if match:
                offset, declaration = match.groups()
                for field, label in normalized.items():
                    if declaration.endswith(' '+field): declaration = label+' '+field
                fields.append([int(offset), declaration])
        sizes = '\n'.join(line.strip() for line in lines if '[sizeof=' in line or 'nvsize=' in line)
        if fields and sizes:
            return {'fields': fields, 'size_alignment': sizes}
    raise ValueError('Clang complete '+name+' layout absent; no ABI pass inferred')


def server_layout(output):
    return record_layout(output, 'swoole::Server', {'rewrite_rules': 'PRIVATE_REWRITE_FIELD'})


def declaration_order(header):
    # Other pinned classes also declare lock_; inspect the actual Server root
    # declaration region, never the first mutex in the entire SDK header.
    anchor='\n    std::string document_root;'
    if header.count(anchor)!=1:
        return False
    region=header.split(anchor,1)[1]
    field=region.find('http_server::RewriteRules rewrite_rules')
    lock=region.find('std::mutex lock_')
    return field>=0 and lock>field


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-rewrite-store-compat.json')
    args = parser.parse_args()
    report = {'passed': False, 'full_gate_passed': False, 'pin': PIN, 'checks': [],
              'scope': 'Pinned unconfigured SDK, full Server direct-member layout/type/copy traits and actual static TU; no configured production/runtime/external SDK/destruction execution'}
    def checked(command, name):
        row = {'name': name, 'command': command, 'free_bytes': shutil.disk_usage(ROOT).free, 'guard_bytes': 4*1024**3}
        report['checks'].append(row)
        if row['free_bytes'] < row['guard_bytes']:
            row['blocked'] = 'unchanged disk guard'; return None
        result = run_isolated(command, timeout=60)
        row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        return result if result.returncode == 0 else None
    with tempfile.TemporaryDirectory(prefix='swr-rewrite-store-sdk-') as temporary:
        tree = Path(temporary); original = tree/'original'; selected = tree/'selected'
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/server/static_handler.cc', 'src/server/master.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = original/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        shutil.copytree(original, selected)
        apply_http_patch(selected, ROOT/'migration/patches/http/0002-static-ranges.patch', report)
        apply_http_patch(selected, ROOT/'migration/patches/http/0003-static-inline.patch', report)
        manifest = ROOT/'migration/patches/integration/manifest.json'
        for entry in json.loads(manifest.read_text())['patches']:
            if entry['upstream_paths'] == ['include/swoole_server.h']:
                proof = apply_patch_verified(selected, manifest.parent/entry['path'], entry['upstream_paths'], entry['sha256'])
                report.setdefault('shared_header_patch_application', []).append(proof)
        header = (selected/'include/swoole_server.h').read_text()
        if 'SWOOLE_RS_HTTP_REWRITE_STORE' not in header or 'http_server::RewriteRules rewrite_rules' not in header:
            report['blocked'] = 'Concrete shared Server field overlay not integrated in this source cohort'
            write_report(args.output, report); return 1
        # Declaration position proves only source member-destruction order.
        report['declaration_order_preserved'] = declaration_order(header)
        code = '''#include "swoole_static_handler.h"
#include <type_traits>
#include <utility>
using T=swoole::Server;
static_assert(!std::is_copy_constructible<T>::value && !std::is_copy_assignable<T>::value,"existing noncopyable Server");
static_assert(!std::is_move_constructible<T>::value && !std::is_move_assignable<T>::value,"existing nonmovable Server");
#if defined(SWOOLE_RS_HTTP_REWRITE_STORE) && SWOOLE_RS_HTTP_REWRITE_STORE
static_assert(std::is_same<decltype(std::declval<T&>().rewrite_rules),swoole::http_server::RewriteRules>::value,"real typed field");
#else
static_assert(std::is_same<decltype(std::declval<T&>().rewrite_rules),std::shared_ptr<std::vector<swoole::http_server::RewriteRule>>>::value,"original field type");
#endif
static_assert(sizeof(T)>0,"force complete Server layout");
'''
        source = tree/'layout.cc'; source.write_text(code)
        flags = ['-DSWOOLE_RS_HTTP', '-fsyntax-only', '-fno-access-control', '-I'+str(ROOT/'native/http')]
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        for standard in ['c++14', 'c++17']:
            baseline = None
            for name, world, macro in [('original', original, []), ('omitted', selected, []), ('off', selected, ['-DSWOOLE_RS_HTTP_REWRITE_STORE=0']), ('on', selected, ['-DSWOOLE_RS_HTTP_REWRITE_STORE=1'])]:
                command = ['c++', '-std='+standard, *flags, *macro, '-I'+str(world/'include'), '-Xclang', '-fdump-record-layouts', str(source)]
                value = checked(command, standard+'-'+name+'-layout')
                if value is None: write_report(args.output, report); return 1
                layout = server_layout(value.stdout+'\n'+value.stderr)
                report['checks'][-1]['server_layout'] = layout
                if baseline is None: baseline = layout
                elif layout != baseline:
                    report['layout_mismatch'] = standard+'-'+name; write_report(args.output, report); return 1
                if world == selected:
                    command = ['c++', '-std='+standard, *flags, *macro, '-I'+str(world/'include'), str(world/'src/server/static_handler.cc')]
                    if checked(command, standard+'-'+name+'-whole-tu') is None: write_report(args.output, report); return 1
        report['passed'] = bool(report['declaration_order_preserved']); write_report(args.output, report)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
