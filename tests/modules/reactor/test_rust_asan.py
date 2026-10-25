#!/usr/bin/env python3
"""Persistent dependency identity checks; no compiler, runtime or large outputs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('reactor_rust_asan',Path(__file__).with_name('rust_asan.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class DependencyIdentity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ['Cargo.toml','Cargo.lock','crates/reactor/Cargo.toml']:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
    def target(self, name='attempt-a', compiler='compiler-a', env=None):
        return runner.dependency_target(self.root,self.root/'private'/name,compiler,env or {})
    def test_reuse_across_unique_final_attempts(self):
        self.assertEqual(self.target()[0],self.target('attempt-b')[0])
        self.assertNotIn('attempt-a',str(self.target()[0]))
    def test_explicit_private_cache_across_distinct_final_parents(self):
        cache=self.root/'own-private-cache'
        one=runner.dependency_target(self.root,self.root/'run-a'/'final','compiler',{},cache)
        two=runner.dependency_target(self.root,self.root/'run-b'/'final','compiler',{},cache)
        self.assertEqual(one,two)
        with self.assertRaises(ValueError):
            runner.dependency_target(self.root,self.root/'final','compiler',{},self.root/'final'/'cache')
    def test_compiler_target_flags_and_graph_changes_isolate(self):
        first=self.target()[0]
        for env in [{'CARGO_BUILD_TARGET':'other-target'},{'RUSTFLAGS':'-Copt-level=1'},{'CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_RUSTFLAGS':'-Copt-level=2'}]:
            self.assertNotEqual(first,self.target(env=env)[0])
        self.assertNotEqual(first,self.target(compiler='compiler-b')[0])
        (self.root/'Cargo.lock').write_text('changed dependency graph')
        self.assertNotEqual(first,self.target()[0])
    def test_flags_not_recorded_and_unrelated_environment_ignored(self):
        # A synthetic marker, never a real environment value or credential.
        path,identity=self.target(env={'RUSTFLAGS':'synthetic-option','UNRELATED_TEST_SETTING':'a'})
        self.assertNotIn('synthetic-option',str(identity))
        self.assertEqual(path,self.target(env={'RUSTFLAGS':'synthetic-option','UNRELATED_TEST_SETTING':'b'})[0])
    def test_missing_identity_fails_closed(self):
        (self.root/'Cargo.lock').unlink()
        with self.assertRaises(FileNotFoundError):self.target()
if __name__=='__main__':unittest.main()
