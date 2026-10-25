#!/usr/bin/env python3
"""Exercise timeout cleanup without running any benchmark or measuring throughput."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('error_benchmark', Path(__file__).with_name('benchmark.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BenchmarkCleanup(unittest.TestCase):
    def test_whole_sample_runner_accepts_existing_benchmark_schema(self):
        with tempfile.TemporaryDirectory(prefix='error-benchmark-whole-sample-') as temporary:
            root = Path(temporary)
            executable = root / 'benchmark'
            executable.write_text(
                f'#!{sys.executable}\n'
                'import json\n'
                'workloads = ["hot", "all-known"]\n'
                'trials = [dict(workload=w, trial=i, rust_ns=110, upstream_ns=100)\n'
                '          for i in range(7) for w in workloads]\n'
                'print(json.dumps(dict(errors=0, trials=trials)))\n')
            executable.chmod(0o755)
            (root / 'manifest.json').write_text(json.dumps({
                'passed': True,
                'sha256': {'benchmark': hashlib.sha256(executable.read_bytes()).hexdigest()},
            }))
            output = root / 'report.json'
            with patch.object(sys, 'argv', ['benchmark.py', '--prepared', str(root), '--output', str(output)]):
                runner.main()
            report = json.loads(output.read_text())
            self.assertTrue(report['passed'])
            self.assertEqual(report['mode'], 'whole_sample')
            self.assertEqual(report['summary']['hot']['throughput_ratio'], 100 / 110)

    def test_state_latency_reports_batch_quantiles_without_conflating_throughput(self):
        with tempfile.TemporaryDirectory(prefix='error-benchmark-latency-shape-') as temporary:
            root = Path(temporary)
            executable = root / 'state-benchmark'
            workloads = ['hit-8', 'miss-8', 'duplicate-8', 'hit-4096', 'miss-4096',
                         'duplicate-4096', 'insert-4096', 'insert-65536', 'concurrent-read-4096']
            executable.write_text(
                f'#!{sys.executable}\n'
                'import json,sys\n'
                'latency = sys.argv[1:] == ["--latency"]\n'
                f'workloads = {workloads!r}\n'
                'rows = []\n'
                'for trial in range(7):\n'
                ' for workload in workloads:\n'
                '  row = dict(workload=workload,trial=trial,operations=1,checksum=1,upstream_ns=100,rust_ns=110,upstream_peak_rss_bytes=1,rust_peak_rss_bytes=1)\n'
                '  if latency:\n'
                '   row.update(upstream_batch_mean_ns_p50=10,upstream_batch_mean_ns_p95=11,upstream_batch_mean_ns_p99=12,rust_batch_mean_ns_p50=20,rust_batch_mean_ns_p95=21,rust_batch_mean_ns_p99=22)\n'
                '  rows.append(row)\n'
                'print(json.dumps(dict(errors=0,timed=True,latency_mode=latency,trials=rows)))\n')
            executable.chmod(0o755)
            (root / 'manifest.json').write_text(json.dumps({
                'passed': True,
                'sha256': {'state-benchmark': hashlib.sha256(executable.read_bytes()).hexdigest()},
                'state_benchmark_workloads': workloads,
            }))
            output = root / 'report.json'
            with patch.object(sys, 'argv', ['benchmark.py', '--prepared', str(root), '--output', str(output),
                                            '--state', '--latency']):
                runner.main()
            report = json.loads(output.read_text())
            self.assertTrue(report['passed'])
            self.assertEqual(report['mode'], 'batch_latency')
            self.assertEqual(report['summary']['hit-8']['batch_mean_ns_p95']['upstream_over_rust'], 11 / 21)

    def test_latency_mode_requires_state_workload(self):
        with patch.object(sys, 'argv', ['benchmark.py', '--prepared', '.', '--output', 'unused.json', '--latency']):
            with self.assertRaises(SystemExit):
                runner.main()

    def test_timeout_kills_descendants_and_preserves_partial_output(self):
        with tempfile.TemporaryDirectory(prefix='error-benchmark-cleanup-') as temporary:
            root = Path(temporary)
            executable = root / 'benchmark'
            marker = root / 'orphan-ran'
            ready = root / 'ready'
            executable.write_text(f'#!{sys.executable}\n'
                                  'import os,time\n'
                                  'print("partial stdout",flush=True)\n'
                                  'os.write(2,b"partial stderr\\n")\n'
                                  'if os.fork()==0:\n'
                                  ' time.sleep(1)\n'
                                  f' open({str(marker)!r},"w").write("orphan")\n'
                                  ' os._exit(0)\n'
                                  f'open({str(ready)!r},"w").close()\n'
                                  'time.sleep(5)\n')
            executable.chmod(0o755)
            (root / 'manifest.json').write_text(json.dumps({
                'passed': True, 'sha256': {'benchmark': hashlib.sha256(executable.read_bytes()).hexdigest()}}))
            output = root / 'report.json'
            communicate = subprocess.Popen.communicate

            def bounded(process, *args, **kwargs):
                if 'timeout' in kwargs:
                    deadline = time.monotonic() + 5
                    while not ready.exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    kwargs['timeout'] = 0.2
                return communicate(process, *args, **kwargs)

            with patch.object(sys, 'argv', ['benchmark.py', '--prepared', str(root), '--output', str(output)]), \
                    patch.object(subprocess.Popen, 'communicate', bounded):
                with self.assertRaises(subprocess.TimeoutExpired):
                    runner.main()
            time.sleep(1.1)
            self.assertFalse(marker.exists(), 'forked workload survived runner timeout')
            report = json.loads(output.read_text())
            self.assertFalse(report['passed'])
            self.assertTrue(report['execution']['interrupted'])
            self.assertIn('partial stdout', report['execution']['stdout'])
            self.assertIn('partial stderr', report['execution']['stderr'])
            self.assertIn('TimeoutExpired', report['error'])


if __name__ == '__main__':
    unittest.main()
