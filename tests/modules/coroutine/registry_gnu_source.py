#!/usr/bin/env python3
"""Bind the GNU registry candidate to captured official package/release sources.
Source checks only: this is not installed-image provenance or Native Linux parity.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body(text, signature):
    # A member declaration may precede its out-of-line definition. Never bind
    # the next unrelated brace after that declaration as the function body.
    import re
    definitions = []
    for match in re.finditer(re.escape(signature), text):
        start = match.start()
        opening = text.find('{', start)
        semicolon = text.find(';', start)
        if opening < 0 or 0 <= semicolon < opening:
            continue
        depth = 1
        end = opening + 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        definitions.append(text[start:end])
    if len(definitions) != 1:
        raise ValueError('Expected one function definition: ' + signature)
    return definitions[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-dir', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    if a.report.exists():
        p.error('Choose a unique receipt')
    r = dict(passed=False, scope=__doc__, native_linux_qualified=False,
             image_provenance_attested=False, activation=False)
    try:
        import re
        package = json.loads((a.candidate_dir / 'qualified-package-candidate.json').read_text())
        mirror = json.loads((a.candidate_dir / 'gnu-mirror-candidate.json').read_text())
        sources = {}
        for name, item in package['files'].items():
            path = a.candidate_dir / 'candidate-headers' / name
            if sha(path) != item['sha256']:
                raise ValueError('Captured header identity changed: ' + name)
            sources[name] = path.read_text()
        for name, item in mirror['files'].items():
            path = a.candidate_dir / ('mirror-' + name)
            if sha(path) != item['sha256']:
                raise ValueError('Captured release source changed: ' + name)
            sources[name] = path.read_text()
        # Source-derived 64-bit table, excluding only the duplicated ABI sentinel.
        table = sources['hashtable-aux.cc'].split('extern const unsigned long __prime_list[] =', 1)[1]
        table = table.split('{', 1)[1].split('};', 1)[0]
        common, conditional = table.split('#if __SIZEOF_LONG__ != 8')
        long64 = conditional.split('#else', 1)[1].split('#endif', 1)[0]
        expected = [int(v) for v in re.findall(r'(\d+)ul', common + long64)]
        if expected[-1] != expected[-2]:
            raise ValueError('Missing duplicated ABI sentinel')
        expected.pop()
        rust = ROOT / 'crates/coroutine/src/registry.rs'
        actual = rust.read_text().split('const GNU_PRIMES: &[u64] = &[', 1)[1].split('];', 1)[0]
        actual = [int(v) for v in re.findall(r'\d+', actual)]
        if actual != expected:
            raise ValueError('Rust prime data differs from captured release')
        header = sources['usr/include/c++/12/bits/hashtable.h']
        selected = {
            'insert_bucket': body(header, '_M_insert_bucket_begin(size_type __bkt, __node_ptr __node)\n'),
            'unique_rehash': body(header, '_M_rehash_aux(size_type __bkt_count, true_type'),
            'next_bucket': body(sources['hashtable_c++0x.cc'], '_Prime_rehash_policy::_M_next_bkt'),
            'need_rehash': body(sources['hashtable_c++0x.cc'], '_M_need_rehash(std::size_t __n_bkt'),
            'clear': body(header, 'clear() noexcept\n'),
        }
        r.update(passed=True, package=package, release=mirror,
                 source_bodies=selected, source_bodies_sha256={k: hashlib.sha256(v.encode()).hexdigest() for k, v in selected.items()},
                 prime_count=len(expected))
    except Exception as e:
        r['error'] = str(e)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r.get(k) for k in ['passed', 'error', 'prime_count', 'native_linux_qualified']}))
    return int(not r['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
