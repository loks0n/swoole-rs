"""Positive codec gates retain exact producer verification and original full plans."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import core_check


class CoreProfiles(unittest.TestCase):
    def test_profiles_forward_only_explicit_scope_with_verified_archive(self):
        for module, flag in [('error', None)]:
            with self.subTest(module=module, flag=flag), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); prefix = root / 'prefix'; archive = prefix / 'lib/libswoole_rs_ffi.a'
                archive.parent.mkdir(parents=True); archive.write_bytes(b'archive identity fixture')
                manifest = root / 'manifest.json'
                manifest.write_text(json.dumps(dict(configure=['--with-swoole-rs=' + str(prefix)],
                    migrated_feature_bits=core_check.MODULES[module][1], inputs=dict(modules=[module],
                    rust_archive_sha256=core_check.sha(archive)))))
                argv = ['core_check.py', '--module', module, '--build-manifest', str(manifest),
                        '--output', str(root/'receipt.json'), '--sanitize', *([flag] if flag else [])]
                with patch.object(core_check, 'ROOT', root), patch('sys.argv', argv), \
                     patch.object(core_check.subprocess, 'run', return_value=SimpleNamespace(returncode=17)) as run:
                    self.assertEqual(core_check.main(), 17)
                    command = run.call_args.args[0]
                    self.assertEqual(command[command.index('--archive') + 1], str(archive))
                    self.assertIn('--sanitize', command)
                    archive.write_bytes(b'changed archive')
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                        core_check.main()
                    self.assertEqual(error.exception.code, 2)
                    self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
