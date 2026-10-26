"""tests/modules/clients/gate.run_shards: every shard runs, counts add up, any failing shard fails."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/modules/clients'))
import gate  # noqa: E402


def script(directory, name, body):
    path = Path(directory) / name
    path.write_text('#!/bin/sh\n' + body + '\n')
    path.chmod(0o755)
    return path


class Shards(unittest.TestCase):
    def test_counts_add_up_per_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            # Shard i of n covers values i, i+n, ... below 10: together exactly 10 values.
            ten = script(directory, 'ten', 'n=0; i=$1; while [ $i -lt 10 ]; do n=$((n+1)); i=$((i+$2)); done; echo $n')
            seven = script(directory, 'seven', 'n=0; i=$1; while [ $i -lt 7 ]; do n=$((n+1)); i=$((i+$2)); done; echo $n')
            for count in [1, 3, 16]:
                self.assertEqual(gate.run_shards([ten, seven], count), [10, 7])

    def test_a_failing_shard_fails_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            failing = script(directory, 'failing', 'if [ $1 -eq 2 ]; then echo mismatch >&2; exit 1; fi; echo 1')
            with self.assertRaises(subprocess.CalledProcessError) as error:
                gate.run_shards([failing], 4)
            self.assertIn(b'mismatch', error.exception.stderr)


if __name__ == '__main__':
    unittest.main()
