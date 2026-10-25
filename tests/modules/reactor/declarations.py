#!/usr/bin/env python3
"""Check actual target-preprocessed reactor C declarations against an archive."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--archive', required=True, type=Path)
p.add_argument('--report', required=True, type=Path)
a = p.parse_args()
header = Path(__file__).resolve().parents[3] / 'native/reactor/swoole_rs_reactor.h'
preprocess = ['cc', '-E', '-P', '-x', 'c', str(header)]
source = subprocess.check_output(preprocess, text=True)
declared = set(re.findall(r'\b(swr_v1_(?:reactor|stream)_\w+)\s*\(', source))
members = [m for m in subprocess.check_output(['ar', '-t', str(a.archive)], text=True).splitlines()
           if m.startswith('swoole_rs_reactor-') and m.endswith('.o')]
assert members, 'archive must contain genuine reactor object members'
outputs = []
with tempfile.TemporaryDirectory(prefix='reactor-declarations-') as temporary:
    for index, member in enumerate(members):
        data = subprocess.check_output(['ar', '-p', str(a.archive), member])
        obj = Path(temporary) / (str(index) + '.o')
        obj.write_bytes(data)
        outputs.append(subprocess.run(['nm', '-g', str(obj)], capture_output=True, text=True, check=True))
defined = {m.group(1) for line in ''.join(n.stdout for n in outputs).splitlines()
           if (m := re.search(r'\b[TDBR] _?(swr_v1_\w+)$', line))}
missing = sorted(declared - defined)
required = {'swr_v1_reactor_epoll_registration', 'swr_v1_reactor_kqueue_registration'}
assert required <= declared, 'generic policies must remain available on every target'
result = {'status': 'failed' if missing else 'passed', 'platform': sys.platform,
          'preprocess': preprocess, 'declarations': sorted(declared), 'missing': missing,
          'members': members, 'nm_stderr': ''.join(n.stderr for n in outputs), 'scope': 'target declarations only; no behavior or parity claim'}
a.report.parent.mkdir(parents=True, exist_ok=True)
a.report.write_text(json.dumps(result, indent=2) + '\n')
print(result['status'], len(declared), 'declarations;', len(missing), 'missing')
sys.exit(bool(missing))
