"""Inert harness-only workload selection; no codec, archive or timing qualification."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('base64_check', HERE / 'check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class PositivePreparation(unittest.TestCase):
    def test_actual_benchmark_selection_and_driver_arguments(self):
        source = (HERE / 'differential.cc').read_text()
        # Exercise the actual whole workload builder with inert codecs, not
        # module/native code. Its only clock operations become fatal guards.
        body = 'static int benchmark' + source.split('static int benchmark', 1)[1].split(
            'static void concurrent_and_fork_calls', 1)[0]
        self.assertEqual(body.count('std::chrono::steady_clock::now()'), 2)
        body = body.replace('std::chrono::steady_clock::now()', 'forbidden_clock()')
        branches = [line.strip() for line in source.splitlines()
                    if 'if (argc == 2' in line and '"--check-' in line]
        self.assertEqual(len(branches), 3)
        self.assertTrue(all('return benchmark(true' in line for line in branches))
        fixture = r'''
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
static size_t encodes = 0, decodes = 0;
static uint8_t random_byte() { return 42; }
static void compare(const std::vector<uint8_t> &, bool encode) {
    ++(encode ? encodes : decodes);
}
static std::chrono::steady_clock::time_point forbidden_clock() {
    throw std::runtime_error("timing forbidden in harness-only test");
}
namespace oracle {
size_t base64_encode(const unsigned char *, size_t n, char *out) {
    std::fill(out, out + n, 'A'); return n;
}
size_t base64_decode(const char *, size_t, char *) { throw std::runtime_error("decoder executed"); }
}
namespace swoole {
using oracle::base64_encode; using oracle::base64_decode;
}
'''
        fixture += body + '\nint main(int argc, char **argv) {\n'
        fixture += '\n'.join(branches) + '\nreturn 2;\n}\n'
        with tempfile.TemporaryDirectory(prefix='base64-preparation-inert-') as directory:
            path = Path(directory)
            for checked in [ROOT, path]:
                if shutil.disk_usage(checked).free < 4 * 1024**3:
                    raise RuntimeError('Unchanged 4GiB guard: ' + str(checked))
            (path / 'control.cc').write_text(fixture)
            subprocess.run(['c++', '-std=c++14', str(path / 'control.cc'), '-o', str(path / 'control')],
                           check=True, capture_output=True, text=True, timeout=60)
            for encode_only, workloads, decodes in [(True, 7, 0), (False, 14, 7)]:
                with self.subTest(encode_only=encode_only):
                    argument, measurement = check.positive_benchmark_arguments(encode_only)
                    result = subprocess.run([str(path / 'control'), argument], check=True,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(json.loads(result.stdout), dict(
                        preflight_passed=True, workloads=workloads, positive_only=True,
                        encode_only=encode_only, encodes=7, decodes=decodes, timed=False))
                    # The actual preparation records this distinct, non-check
                    # command only for a future acknowledged measurement lease.
                    self.assertIn('"' + measurement + '") return benchmark(false, true', source)
            self.assertEqual(subprocess.run([str(path / 'control'), '--encode-positive-benchmark'],
                                            capture_output=True, timeout=10).returncode, 2)


if __name__ == '__main__':
    unittest.main()
