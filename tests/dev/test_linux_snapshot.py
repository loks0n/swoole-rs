"""Exact linked-worktree commits through one object store, with private refs/index."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.linux_dev import source_snapshot


def git(directory, *args):
    return subprocess.check_output(['git', '-C', str(directory), *args], stderr=subprocess.PIPE, text=True).strip()


class LinuxSnapshot(unittest.TestCase):
    def test_linked_sources_share_objects_but_private_head_and_index_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source'; source.mkdir()
            git(source, 'init', '-q')
            git(source, 'config', 'user.name', 'Snapshot fixture')
            git(source, 'config', 'user.email', 'fixture@example.invalid')
            (source/'initial.txt').write_text('initial\n')
            git(source, 'add', '.')
            git(source, 'commit', '-qm', 'initial')
            first, objects = source_snapshot(source)
            linked = Path(directory)/'linked'
            git(source, 'worktree', 'add', '-q', '--detach', str(linked), first)
            self.assertEqual(source_snapshot(linked), (first, objects))
            (source/'next.txt').write_text('next\n')
            git(source, 'add', 'next.txt'); git(source, 'commit', '-qm', 'next')
            second, same = source_snapshot(source)
            self.assertEqual(same, objects)
            self.assertNotEqual(first, second)
            private = Path(directory)/'private'; private.mkdir()
            git(private, 'init', '-q')
            alternates = private/'.git/objects/info/alternates'
            alternates.write_text(str(objects)+'\n')
            git(private, 'cat-file', '-e', second+'^{commit}')
            git(private, 'reset', '--mixed', '-q', second)
            self.assertEqual(git(private, 'show', 'HEAD:next.txt'), 'next')
            git(private, 'reset', '--mixed', '-q', first)
            self.assertEqual(git(source, 'rev-parse', 'HEAD'), second)
            self.assertEqual(git(linked, 'rev-parse', 'HEAD'), first)
            self.assertFalse(list((private/'.git/objects/pack').glob('*.pack')))
            missing = subprocess.run(['git','-C',str(private),'cat-file','-e','0'*40+'^{commit}'], capture_output=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertEqual(git(private, 'rev-parse', 'HEAD'), first)
            (objects/'info/alternates').write_text(str(private/'.git/objects')+'\n')
            with self.assertRaisesRegex(ValueError, 'external alternates'):
                source_snapshot(source)
