"""Prerequisite errors must not start services or disguise original failures."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('collections_originals', Path(__file__).with_name('originals.py'))
originals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(originals)


class Prerequisites(unittest.TestCase):
    def invoke(self, folder, *, missing=False, warning=False, unknown=False):
        root = Path(folder)
        extension = root / 'redis.so'
        if not missing:
            extension.write_bytes(b'explicit fixture extension')
        output = root / 'report.json'
        argv = ['originals', '--source', str(root), '--source-ref', 'fixture',
                '--engine', 'native=native.so', '--engine', 'selected=selected.so',
                '--build-manifest', 'manifest.json', '--archive', 'archive.a',
                '--redis-extension', str(extension), '--output', str(output)]
        if unknown:
            argv += ['--case', 'tests/outside.phpt']
        probe = subprocess.CompletedProcess([], 0, json.dumps(dict(class_=True)), '')
        probe.stdout = json.dumps({'class': True, 'redis': 'fixture', 'php': 'fixture', 'extension_dir': folder})
        probe.stderr = 'loader warning retained' if warning else ''
        fake_inventory = dict(repository='fixture', tests=[{'path': 'tests/inside.phpt'}], support_files=[])
        with patch.object(sys, 'argv', argv), patch.object(originals, 'require_build_space'), \
                patch.object(originals.subprocess, 'run', return_value=probe) as run, \
                patch.object(originals, 'inventory', return_value=fake_inventory), \
                patch.object(originals, 'ManagedRedis') as service, redirect_stdout(io.StringIO()):
            status = originals.main()
        return status, json.loads(output.read_text()), run.call_count, service.call_count

    def test_missing_extension_refuses_before_php_service_or_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            status, report, commands, services = self.invoke(folder, missing=True)
        self.assertEqual((status, commands, services), (1, 0, 0))
        self.assertIn('prerequisite is missing', report['error'])
        self.assertFalse(report['baseline_replaced'])

    def test_extension_warning_retained_and_service_never_started(self):
        with tempfile.TemporaryDirectory() as folder:
            status, report, commands, services = self.invoke(folder, warning=True)
        self.assertEqual((status, commands, services), (1, 1, 0))
        self.assertEqual(report['commands'][0]['stderr'], 'loader warning retained')
        self.assertNotIn('originals', report)

    def test_unregistered_case_refuses_before_attested_runtime_or_service(self):
        with tempfile.TemporaryDirectory() as folder:
            status, report, commands, services = self.invoke(folder, unknown=True)
        self.assertEqual((status, commands, services), (1, 1, 0))
        self.assertIn('outside the complete original inventory', report['error'])


class ServiceIdentity(unittest.TestCase):
    def test_wrong_native_pid_refuses_and_owned_process_is_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            record = {}
            service = originals.ManagedRedis(Path(folder), record)
            process = Mock(pid=41, returncode=0)
            process.poll.return_value = None
            service.process, service.cli, service.port = process, 'redis-cli', 12345
            info = subprocess.CompletedProcess([], 0, 'run_id:fixture\nprocess_id:99\n', '')
            with patch.object(service, 'command', return_value=info):
                with self.assertRaisesRegex(ValueError, 'managed Redis PID'):
                    service.observe()
            process.poll.side_effect = [None, 0]
            service.close()
            process.terminate.assert_called_once()
            self.assertTrue(record['removed'])

    def test_non_loopback_docker_publication_refuses_and_cleans_up(self):
        image = 'sha256:' + 'a' * 64
        container = 'b' * 64
        def execute(command, **kwargs):
            if command[:3] == ['docker', 'image', 'inspect']:
                output = json.dumps([{'Id': image}])
            elif command[:2] == ['docker', 'run']:
                output = container
            elif command[:2] == ['docker', 'inspect']:
                output = json.dumps([{'Image': image, 'NetworkSettings': {'Ports': {
                    '6379/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '12345'}]}}}])
            else:
                output = ''
            return subprocess.CompletedProcess(command, 0, output, '')
        with tempfile.TemporaryDirectory() as folder:
            record = {}
            service = originals.ManagedRedis(Path(folder), record, image=image)
            with patch.object(originals.subprocess, 'run', side_effect=execute):
                with self.assertRaisesRegex(ValueError, 'publication differs'):
                    service.__enter__()
        self.assertTrue(record['removed'])
        self.assertTrue(record['network_removed'])

    def test_failed_docker_cleanup_does_not_claim_absence(self):
        with tempfile.TemporaryDirectory() as folder:
            record = {}
            service = originals.ManagedRedis(Path(folder), record, image='fixture')
            service.container, service.network = 'b' * 64, 'owned-fixture'
            failure = subprocess.CompletedProcess([], 1, '', 'daemon unavailable')
            with patch.object(originals.subprocess, 'run', return_value=failure):
                service.close()
        self.assertFalse(record['removed'])
        self.assertFalse(record.get('network_removed', False))
        self.assertEqual(len(record['cleanup_errors']), 2)


if __name__ == '__main__':
    unittest.main()
