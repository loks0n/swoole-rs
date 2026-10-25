"""Local preflight reports resource and interpreter facts without repairing them."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import dev_environment as env


class Environment(unittest.TestCase):
    def selected(self):
        return {name: 'chosen-' + name for name in
                ['python', 'cc', 'cxx', 'rustc', 'cargo', 'php', 'php_config', 'make', 'openssl']}

    def probe(self, executable, arguments, timeout):
        identity = {'executable': '/chosen/python', 'version': 'fixture', 'ssl_backend': 'fixture SSL',
                    'tls': {v: {'advertised': True, 'configuration_accepted': True} for v in ['1.2', '1.3']}}
        stdout = json.dumps(identity) if '-c' in arguments else json.dumps({'version': '8.5', 'zts': False}) if '-r' in arguments else 'fixture version'
        if executable == 'chosen-php_config' and arguments == ['--version']:
            stdout = '8.5'
        return {'status': 'available', 'resolved': executable, 'stdout': stdout, 'command': [executable, *arguments]}

    def snapshot(self, root, free=env.MIN_FREE_BYTES, override=None, probe=None):
        patches = {'SWOOLE_RS_MIN_FREE_BYTES': override} if override is not None else {}
        with patch.dict(os.environ, patches, clear=True), patch.object(env, 'probe', side_effect=probe or self.probe), \
                patch.object(env.sys, 'platform', 'linux'), \
                patch.object(env, 'mounts', return_value=([{'mountpoint': str(Path(root).resolve()), 'filesystem_type': 'tmpfs', 'ram_backed': True}], None)), \
                patch.object(env.shutil, 'disk_usage', return_value=SimpleNamespace(total=20 * 1024**3, used=1, free=free)):
            return env.collect({'source': root, 'native': Path(root) / 'native/not-created',
                                'output': Path(root) / 'reports/not-created'}, self.selected())

    def test_guard_boundary_and_future_directories_measure_real_existing_ancestor(self):
        with tempfile.TemporaryDirectory() as root:
            report = self.snapshot(root)
            self.assertEqual(report['status'], 'ready')
            self.assertEqual(report['minimum_free_bytes'], 4294967296)
            self.assertEqual(report['filesystems']['native']['measured_at'], str(Path(root).resolve()))
            self.assertFalse(report['filesystems']['native']['exists'])
            self.assertTrue(report['filesystems']['native']['ram_backed'])
            self.assertFalse((Path(root) / 'native').exists())
            low = self.snapshot(root, free=env.MIN_FREE_BYTES - 1)
            self.assertEqual(low['status'], 'blocked')
            self.assertFalse(low['passed'])
            self.assertEqual({f['subject'] for f in low['findings']}, {'source', 'native', 'output'})

    def test_unsupported_tls_context_never_auto_switches_chosen_python(self):
        def unsupported(executable, arguments, timeout):
            result = self.probe(executable, arguments, timeout)
            if '-c' in arguments:
                data = json.loads(result['stdout'])
                data['tls']['1.3'] = {'advertised': False, 'configuration_accepted': False,
                                      'error': 'Unsupported protocol version'}
                result['stdout'] = json.dumps(data)
            return result
        with tempfile.TemporaryDirectory() as root:
            report = self.snapshot(root, probe=unsupported)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['tools']['python']['resolved'], 'chosen-python')
        self.assertEqual(report['findings'][0]['subject'], 'python TLS 1.3')

    def test_conflicting_advertised_and_accepted_tls_evidence_stays_blocked_and_raw(self):
        def conflicting(executable, arguments, timeout):
            result = self.probe(executable, arguments, timeout)
            if '-c' in arguments:
                data = json.loads(result['stdout'])
                data['tls']['1.2']['advertised'] = False
                result['stdout'] = json.dumps(data)
            return result
        with tempfile.TemporaryDirectory() as root:
            report = self.snapshot(root, probe=conflicting)
        self.assertEqual(report['status'], 'blocked')
        observed = report['tools']['python']['identity']['tls']['1.2']
        self.assertFalse(observed['advertised'])
        self.assertTrue(observed['configuration_accepted'])
        self.assertIn('no handshake performed', report['findings'][0]['detail'])

    def test_mixed_php_runtime_and_sdk_selection_blocks_without_auto_repair(self):
        def mismatched(executable, arguments, timeout):
            result = self.probe(executable, arguments, timeout)
            if executable == 'chosen-php_config' and arguments == ['--version']:
                result['stdout'] = '8.2.35'
            return result
        with tempfile.TemporaryDirectory() as root:
            report = self.snapshot(root, probe=mismatched)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['findings'][0]['subject'], 'php/config selection')
        self.assertEqual(report['tools']['php']['identity']['version'], '8.5')
        self.assertEqual(report['tools']['php_config']['stdout'], '8.2.35')

    def test_guard_override_is_observed_without_lowering_fixed_threshold_or_leaking_invalid_value(self):
        with tempfile.TemporaryDirectory() as root:
            report = self.snapshot(root, override='0')
            self.assertEqual(report['status'], 'blocked')
            self.assertEqual(report['configured_guard_bytes'], 0)
            self.assertEqual(report['minimum_free_bytes'], 4294967296)
            invalid = self.snapshot(root, override='private-invalid-value')
            self.assertEqual(invalid['status'], 'unavailable')
            self.assertNotIn('private-invalid-value', json.dumps(invalid))

    def test_linux_mounts_keep_bind_ram_and_escaped_path_metadata_without_mount_sources(self):
        rows = env.linux_mounts('1 0 1:1 / / rw - overlay secret-source rw\n'
                               '2 1 1:2 / /ram\\040files rw - tmpfs private-source rw\n')
        self.assertEqual(rows[1]['mountpoint'], '/ram files')
        self.assertTrue(rows[1]['ram_backed'])
        self.assertEqual(rows[1]['ram_evidence'], 'kernel mountinfo tmpfs')
        self.assertIsNone(rows[0]['ram_backed'])
        self.assertNotIn('private-source', json.dumps(rows))

    def test_darwin_volume_name_alone_never_proves_ram_backing(self):
        text = '/dev/disk9 on /Volumes/LooksLikeRAM (hfs, local)\n'
        self.assertIsNone(env.darwin_mounts(text, {})[0]['ram_backed'])
        images = {'images': [{'image-path': 'ram://1234', 'system-entities': [
            {'mount-point': '/Volumes/LooksLikeRAM'}]}]}
        self.assertTrue(env.darwin_mounts(text, images)[0]['ram_backed'])
        self.assertEqual(env.darwin_mounts(text, images)[0]['ram_evidence'], 'hdiutil ram:// image')

    def test_darwin_firmlink_filesystem_uses_df_mountpoint_instead_of_path_prefix(self):
        with tempfile.TemporaryDirectory() as root, patch.object(env.sys, 'platform', 'darwin'), \
                patch.object(env, 'execute', return_value=SimpleNamespace(returncode=0,
                    stdout=b'Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk3 10 1 9 10% /System/Volumes/Data\n')):
            row = env.filesystem(root, [{'mountpoint': '/', 'filesystem_type': 'apfs', 'ram_backed': None},
                                        {'mountpoint': '/System/Volumes/Data', 'filesystem_type': 'apfs', 'ram_backed': None}])
            self.assertEqual(row['mountpoint'], '/System/Volumes/Data')

    def test_missing_timed_out_truncated_and_failed_probes_stay_unavailable(self):
        with patch.object(env.shutil, 'which', return_value=None), patch.object(env, 'execute') as run:
            self.assertEqual(env.probe('absent', ['--version'])['status'], 'unavailable')
            run.assert_not_called()
        for result in [SimpleNamespace(returncode=1, stdout=b'private-config-output', stderr=b'private-environment'),
                       SimpleNamespace(returncode=0, stdout=b'x' * (env.MAX_TEXT + 1), stderr=b''),
                       SimpleNamespace(returncode=0, stdout=b'', stderr=b'')]:
            with patch.object(env.shutil, 'which', return_value='/chosen/tool'), patch.object(env, 'execute', return_value=result):
                row = env.probe('chosen', ['--version'])
                self.assertEqual(row['status'], 'unavailable')
                self.assertLessEqual(len(row['stdout']), env.MAX_TEXT)
                self.assertNotIn('private-config-output', json.dumps(row))
                self.assertNotIn('private-environment', json.dumps(row))
        with patch.object(env.shutil, 'which', return_value='/chosen/tool'), \
                patch.object(env, 'execute', side_effect=subprocess.TimeoutExpired('chosen', 1)):
            self.assertEqual(env.probe('chosen', ['--version'])['error'], 'TimeoutExpired')

    def test_malformed_identity_and_unavailable_filesystem_never_pass(self):
        def malformed(executable, arguments, timeout):
            row = self.probe(executable, arguments, timeout)
            if '-c' in arguments:
                row['stdout'] = '{"tls": []}'
            return row
        with tempfile.TemporaryDirectory() as root:
            report = self.snapshot(root, probe=malformed)
            self.assertEqual(report['status'], 'unavailable')
            self.assertEqual(report['tools']['python']['error'], 'Malformed identity JSON')
            with patch.object(env.shutil, 'disk_usage', side_effect=PermissionError('private payload')):
                row = env.filesystem(root, [])
            self.assertEqual(row['status'], 'unavailable')
            self.assertNotIn('private payload', json.dumps(row))
            with patch.object(Path, 'stat', side_effect=PermissionError('private path details')):
                row = env.filesystem(root, [])
            self.assertEqual(row['status'], 'unavailable')
            self.assertNotIn('private path details', json.dumps(row))

    def test_version_execution_is_shell_free_offline_and_does_not_change_parent_environment(self):
        with patch.dict(os.environ, {'PRIVATE_TOKEN': 'not-for-output'}, clear=True), \
                patch.object(env.subprocess, 'run', return_value=SimpleNamespace()) as run:
            env.execute(['/chosen/rustc', '--version'])
            args, kwargs = run.call_args
            self.assertEqual(args[0], ['/chosen/rustc', '--version'])
            self.assertNotIn('shell', kwargs)
            self.assertEqual(kwargs['env']['RUSTUP_AUTO_INSTALL'], '0')
            self.assertEqual(kwargs['env']['CARGO_NET_OFFLINE'], 'true')
            self.assertNotIn('RUSTUP_AUTO_INSTALL', os.environ)

    def test_cli_json_and_human_output_keep_explicit_paths_and_scope(self):
        with tempfile.TemporaryDirectory() as root:
            report = self.snapshot(root)
            args = ['dev_environment.py', '--source-root', root, '--native-root', root, '--output-root', root]
            for mode in [[], ['--json']]:
                output = io.StringIO()
                with patch.object(env.sys, 'argv', args + mode), patch.object(env, 'collect', return_value=report) as collect, \
                        patch('sys.stdout', output):
                    self.assertEqual(env.main(), 0)
                    self.assertEqual(collect.call_args[0][0]['source'], Path(root))
                if mode:
                    self.assertEqual(json.loads(output.getvalue())['minimum_free_bytes'], 4294967296)
                else:
                    self.assertIn('no build, network, handshake', output.getvalue())
                    self.assertIn('RAM=True', output.getvalue())

    def test_cli_has_no_lower_guard_option_and_refuses_nonfinite_timeouts(self):
        args = ['dev_environment.py', '--source-root', '/', '--native-root', '/', '--output-root', '/']
        for invalid in [['--minimum-free-bytes', '0'], ['--timeout', 'nan'], ['--timeout', 'inf'], ['--timeout', '-1']]:
            with patch.object(env.sys, 'argv', args + invalid), patch('sys.stderr', io.StringIO()), \
                    patch.object(env, 'collect') as collect:
                with self.assertRaises(SystemExit) as result:
                    env.main()
                self.assertEqual(result.exception.code, 2)
                collect.assert_not_called()

    def test_actual_selected_python_probe_uses_only_local_ssl_configuration(self):
        row = env.probe(sys.executable, ['-I', '-S', '-B', '-c', env.PYTHON_IDENTITY])
        self.assertEqual(row['status'], 'available', row)
        identity = json.loads(row['stdout'])
        self.assertTrue(identity['executable'])
        self.assertEqual(set(identity['tls']), {'1.2', '1.3'})
        self.assertIn('no socket or handshake', identity['scope'])


if __name__ == '__main__':
    unittest.main()
