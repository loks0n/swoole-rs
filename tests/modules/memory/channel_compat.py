#!/usr/bin/env python3
"""Compare Channel source initialization under the pinned and the hybrid build's headers.

Compiler-only observations. No runtime object, fixture, network or timing workload.
Physical ABI assertions and source initialization domains are separate gates.
"""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True, help='Rust archive of the hybrid build under test')
    parser.add_argument('--cxx', default='c++')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'passed': False, 'scope': __doc__, 'upstream_commit': PIN, 'cases': [], 'commands': []}
    def run(command):
        result = run_isolated(list(map(str, command)), timeout=30)
        report['commands'].append({'argv': list(map(str, command)), 'returncode': result.returncode,
                                   'stdout': result.stdout, 'stderr': result.stderr})
        return result
    try:
        hybrid_source, hybrid_flags = hybrid_tree(args.archive)
        report['hybrid_tree'] = str(hybrid_source)
        report['compiler'] = run([*shlex.split(args.cxx), '--version']).stdout
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        archive = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include'], timeout=15)
        with tempfile.TemporaryDirectory(prefix='swr-channel-compat-') as temporary:
            root = Path(temporary)
            prefix = '#include "swoole_channel.h"\n#include <type_traits>\nusing swoole::Channel;\n'
            suffix = '\nstatic_assert(std::is_standard_layout<Channel>::value && std::is_trivially_copyable<Channel>::value, "traits");\nstatic_assert(sizeof(Channel)==80 && value.head==1 && value.tail==2 && value.size==128 && value.tail_tag==1 && value.num==3 && value.max_num==4 && value.bytes==9 && value.flags==6 && value.maxlen==32 && value.mem==nullptr && value.lock==nullptr && value.notify_pipe==nullptr, "field initialization");\n'
            cases = [('flat', standard, 'constexpr Channel value{1,2,128,0,1,3,4,9,6,32,nullptr,nullptr,nullptr};')
                     for standard in ['c++14', 'c++17', 'c++20']]
            cases.append(('designated', 'c++20', 'constexpr Channel value{.head=1,.tail=2,.size=128,.head_tag=0,.tail_tag=1,.num=3,.max_num=4,.bytes=9,.flags=6,.maxlen=32,.mem=nullptr,.lock=nullptr,.notify_pipe=nullptr};'))
            for engine in ['upstream', 'rust']:
                tree = root / engine
                tree.mkdir()
                if engine == 'upstream':
                    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                        for member in bundle:
                            if member.isfile():
                                path = tree / member.name
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_bytes(bundle.extractfile(member).read())
                    headers = ['-DSWOOLE_RS_MEMORY=1', '-I' + str(tree / 'include')]
                else:
                    # The hybrid build's fully patched headers, with its module switches.
                    headers = hybrid_flags
                for name, standard, definition in cases:
                    source = tree / (name + '.cc')
                    source.write_text(prefix + definition + suffix)
                    result = run([*shlex.split(args.cxx), '-std=' + standard, *headers, *flags, '-fsyntax-only', source])
                    report['cases'].append({'engine': engine, 'case': name, 'standard': standard,
                                            'passed': result.returncode == 0, 'command_index': len(report['commands'])-1})
                if engine == 'rust':
                    includes = [flag for flag in hybrid_flags if flag.startswith('-I')]
                    command=[*shlex.split(args.cxx), '-std=c++14', *includes, *flags, '-fsyntax-only', tree/'flat.cc']
                    rejected=run(command)
                    report['missing_feature_rejected']=(rejected.returncode != 0 and
                        'Memory overlay requires --enable-swoole-rs-memory' in rejected.stderr)
                    (tree/'config.h').write_text(''.join('#define ' + flag[2:] + ' 1\n' for flag in hybrid_flags if flag.startswith('-D')))
                    configured=run([*command[:-1], '-I'+str(tree), '-DHAVE_CONFIG_H', command[-1]])
                    report['config_header_feature_accepted']=configured.returncode==0
            report['passed'] = (all(c['passed'] for c in report['cases']) and
                                report.get('missing_feature_rejected') is True and
                                report.get('config_header_feature_accepted') is True)
            report['source_divergences'] = [{'case': name, 'standard': standard}
                for name, standard, _ in cases if any(c['passed'] and c['engine']=='upstream' and c['case']==name and c['standard']==standard for c in report['cases'])
                and any(not c['passed'] and c['engine']=='rust' and c['case']==name and c['standard']==standard for c in report['cases'])]
    except Exception as error:
        report['error'] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ['passed', 'source_divergences', 'error']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
