#!/usr/bin/env python3
"""Compare exact pinned native bodies and generated real callers at fake IO boundaries."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import run_isolated, write_report
from overlay import ROOT, PIN, original, generated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build = ROOT / 'target/framing-trace'
    build.mkdir(parents=True, exist_ok=True)
    own = ROOT / 'tests/modules/framing'
    for name in ['swoole.h', 'swoole_string.h', 'swoole_socket.h']:
        (build / name).write_text('#include "trace.h"\n')
    for name in ['swoole_protocol.h', 'swoole_mime_type.h']:
        (build / name).write_text(original('include/' + name))
    string = original('src/core/string.cc')
    start = string.index('ssize_t String::split(')
    (build / 'split.cpp').write_text('#include "trace.h"\nnamespace swoole {\n' + string[start:string.index('\n}  // namespace', start)] + '\n}\n')
    archive = build / 'libframing.a'
    commands = [['rustc', '--edition=2024', '--crate-name', 'swoole_rs_framing', '--crate-type=staticlib', '-O', '-Dwarnings', str(ROOT / 'crates/framing/src/lib.rs'), '-o', str(archive)]]
    report = {'upstream_pin': PIN, 'scope': 'Exact pinned C++ bodies vs actual generated M18 callers; instrumented IO/storage, not real socket or PHP validation', 'passed': False, 'commands': [], 'engines': []}
    try:
        for engine in ['upstream', 'rust']:
            for path, text in generated().items():
                (build / (engine + '-' + Path(path).name)).write_text(original(path) if engine == 'upstream' else text)
            binary = build / engine
            command = ['c++', '-std=c++14', '-O2', '-UNDEBUG', '-I' + str(build), '-I' + str(own), '-I' + str(ROOT / 'native/framing'), str(own / 'trace.cpp'), str(build / 'split.cpp'), *[str(build / (engine + '-' + Path(path).name)) for path in generated()], '-o', str(binary)]
            if engine == 'rust':
                command.append(str(archive))
            commands.append(command)
            for cmd in commands:
                result = run_isolated(cmd, timeout=120)
                report['commands'].append({'argv': cmd, 'exit': result.returncode, 'stderr': result.stderr})
                if result.returncode:
                    raise RuntimeError(engine + ' compilation failed')
            commands.clear()
            result = run_isolated([str(binary)], timeout=120)
            output = build / (engine + '.txt')
            output.write_text(result.stdout)
            (build / (engine + '.stderr')).write_text(result.stderr)
            report['engines'].append({'name': engine, 'exit': result.returncode, 'output': str(output), 'lines': len(result.stdout.splitlines())})
            if result.returncode:
                raise RuntimeError(engine + ' trace failed')
        upstream = (build / 'upstream.txt').read_text().splitlines()
        rust = (build / 'rust.txt').read_text().splitlines()
        differences = [{'line': n, 'upstream': a, 'rust': b} for n, (a, b) in enumerate(zip(upstream, rust), 1) if a != b]
        report.update(differences=differences[:50], total_differences=len(differences), passed=len(upstream) == len(rust) and not differences)
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps(report))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
