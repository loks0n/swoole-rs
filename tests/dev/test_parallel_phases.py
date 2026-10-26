"""dev.py runs independent phases at once, but never past a barrier, a serial phase or a report it reads."""
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import dev


class ParallelPhases(unittest.TestCase):
    def run_plan(self, planned, jobs):
        """Run `planned` with each phase sleeping briefly; return the overlap seen and the report."""
        lock, running, overlaps = threading.Lock(), set(), []

        def fake(command, **_):
            name = command[0]
            with lock:
                overlaps.append((name, frozenset(running)))
                running.add(name)
            time.sleep(0.05)
            with lock:
                running.discard(name)
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(dev, 'ROOT', root), patch.object(dev, 'plan', return_value=planned), \
                 patch.object(dev, 'execute', side_effect=fake), \
                 patch('sys.argv', ['dev.py', 'integrate', '--module', 'buffer', '--jobs', str(jobs)]):
                self.assertEqual(dev.main(), 0)
            report = json.loads(next(root.glob('target/reports/dev/*/loop.json')).read_text())
        return dict(overlaps), report

    def test_independent_phases_overlap_but_barriers_and_serial_phases_run_alone(self):
        planned = [('a', ['a']), ('b', ['b']), ('ownership', ['ownership']), ('c', ['c']), ('d', ['d']),
                   ('e-originals', ['e-originals']), ('f', ['f'])]
        overlaps, report = self.run_plan(planned, 4)
        self.assertEqual(overlaps['b'], {'a'})
        self.assertEqual(overlaps['ownership'], set())
        self.assertEqual(overlaps['e-originals'], set())
        self.assertNotIn('ownership', overlaps['c'] | overlaps['d'] | overlaps['f'])
        self.assertTrue(overlaps['d'] or overlaps['f'], 'later independent phases should overlap')
        # The serial phase nothing reads from runs after the parallel work, but rows stay in plan order.
        self.assertEqual([row['phase'] for row in report['phases']], [name for name, _ in planned])

    def test_a_phase_waits_for_the_report_it_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            commands = [('producer', ['producer', '--output', str(reports / 'producer.json')]),
                        ('other', ['other']),
                        ('consumer', ['consumer', '--native-report', str(reports / 'producer.json')])]
            dependencies = dev.phase_dependencies(commands, reports)
        self.assertEqual(dependencies, {'producer': set(), 'other': set(), 'consumer': {'producer'}})

    def test_one_job_runs_phases_one_at_a_time(self):
        overlaps, _ = self.run_plan([('a', ['a']), ('b', ['b']), ('c', ['c'])], 1)
        self.assertEqual(set(overlaps.values()), {frozenset()})


if __name__ == '__main__':
    unittest.main()
