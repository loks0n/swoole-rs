"""tools/badges.py counts upstream lines the patch set deletes (net), graduated leaves and passing PHPTs."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import badges  # noqa: E402


def diff(path, old, new, context):
    """A one-hunk git patch replacing `old` lines with `new` lines at the top of `path`,
    followed by one unchanged `context` line (git apply needs context)."""
    body = ''.join(f'-{line}\n' for line in old) + ''.join(f'+{line}\n' for line in new) + f' {context}\n'
    return (f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n'
            f'@@ -1,{len(old) + 1} +1,{len(new) + 1} @@\n{body}')


class Badges(unittest.TestCase):
    def test_net_upstream_deletions_over_first_party_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            source, patches = Path(directory) / 'src-tree', Path(directory) / 'patches'
            (source / 'src').mkdir(parents=True)
            (source / 'ext-src').mkdir()
            (source / 'thirdparty').mkdir()
            patches.mkdir()
            (source / 'src/a.cc').write_text(''.join(f'line {n}\n' for n in range(10)))
            (source / 'ext-src/php_swoole_library.h').write_text('x\n' * 1000)  # not counted
            (source / 'thirdparty/lib.c').write_text('x\n' * 1000)  # not counted
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            # The first patch replaces 3 upstream lines with 2 lines of glue; the second
            # removes that glue again. Only the 3 upstream lines count as deleted.
            first = patches / '0001.patch'
            first.write_text(diff('src/a.cc', ['line 0', 'line 1', 'line 2'], ['glue 1', 'glue 2'], 'line 3'))
            second = patches / '0002.patch'
            second.write_text(diff('src/a.cc', ['glue 1', 'glue 2'], [], 'line 3'))
            rows = [{'path': str(first), 'upstream_paths': ['src/a.cc'], 'sha256': None},
                    {'path': str(second), 'upstream_paths': ['src/a.cc'], 'sha256': None}]
            self.assertEqual(badges.replaced(source, rows), (3, 10))

    def test_phpt_counts_hybrid_passes_over_every_pinned_test(self):
        rows = [{'test': 'a', 'engine': 'upstream', 'status': 'passed'}, {'test': 'a', 'engine': 'hybrid', 'status': 'passed'},
                {'test': 'b', 'engine': 'upstream', 'status': 'passed'}, {'test': 'b', 'engine': 'hybrid', 'status': 'failed'},
                {'test': 'c', 'engine': 'upstream', 'status': 'skipped'}, {'test': 'c', 'engine': 'hybrid', 'status': 'skipped'}]
        self.assertEqual(badges.phpt_passing(rows), (1, 3))

    def test_every_leaf_is_a_module(self):
        self.assertLessEqual(set(badges.LEAF), set(badges.MODULES))


if __name__ == '__main__':
    unittest.main()
