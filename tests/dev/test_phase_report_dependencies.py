"""Reject leaf selections whose report inputs cannot exist in the new run."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PhaseReports(unittest.TestCase):
    def test_report_consumers_require_their_parent_phase(self):
        for module, child, parent in [
            ('phphelpers','phphelpers-async-sqlite-sdk','phphelpers-sdk'),
            ('phphelpers','phphelpers-async-odbc-sdk','phphelpers-sdk'),
            ('phpevents','phpevents-alias-original','phpevents-originals-manifest'),
            ('base64','base64-consumers-upstream','reference-identity')]:
            with self.subTest(child=child):
                command=[sys.executable,'tools/dev.py','integrate','--module',module,'--phase',child,'--plan']
                failed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(failed.returncode,2,failed.stdout+failed.stderr)
                self.assertIn('requires report-producing phases',failed.stderr)
                self.assertIn(parent,failed.stderr)
                result=subprocess.run(command+['--phase',parent],cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                phases=[row['phase'] for row in json.loads(result.stdout)]
                self.assertEqual(set(phases),{parent,child})
                self.assertLess(phases.index(parent),phases.index(child))

    def test_independent_selection_stays_independent(self):
        result=subprocess.run([sys.executable,'tools/dev.py','integrate','--module','buffer',
            '--phase','buffer-string-compatibility','--plan'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual([r['phase'] for r in json.loads(result.stdout)],['buffer-string-compatibility'])
