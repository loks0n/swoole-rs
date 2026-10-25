"""A prepared checksum must not authorize measurement of an unmatched pair."""
import copy
import json
import tempfile
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('collections_prepare_benchmark', Path(__file__).with_name('prepare_benchmark.py'))
prepared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepared)


class MatchedProfiles(unittest.TestCase):
    def pair(self):
        native = {'inputs': dict(fix_halfclose=False, compiler='same captured compiler',
                                upstream_commit='same pin', effective_cxxflags='-g -O2', php='8.test', php_config='same SDK', phpize='/same/phpize', effective_cppflags='', effective_configure=['./configure','--enable-swoole-stdext','--without-swoole-rs'])}
        selected = copy.deepcopy(native)
        selected['rust_compilation'] = {'artifact': {'profile': dict(opt_level='3', debug_assertions=False)}}
        return selected, native

    def test_missing_attestations_never_match_by_two_null_values(self):
        blockers = prepared.eligibility({}, {})
        self.assertTrue(any('compiler identities are missing' in item for item in blockers))
        self.assertTrue(any('halfclose profile identities are missing' in item for item in blockers))
        self.assertTrue(any('reference source identities are missing' in item for item in blockers))

    def test_correction_difference_remains_a_matching_blocker(self):
        selected, native = self.pair()
        selected['inputs']['fix_halfclose'] = True
        self.assertIn('Native halfclose correction differs between the artifact profiles', prepared.eligibility(selected, native))

    def test_optimization_flags_missing_are_not_inferred_from_rust_release(self):
        selected, native = self.pair()
        for manifest in [selected, native]:
            del manifest['inputs']['effective_cxxflags']
        self.assertTrue(any('C++ optimization flags are not attested' in item for item in prepared.eligibility(selected, native)))

    def test_trailing_O0_overrides_earlier_optimized_flag(self):
        selected, native = self.pair()
        for manifest in [selected, native]:
            manifest['inputs']['effective_cxxflags'] = '-O3 -g -O0'
        self.assertIn('Native C++ profile is not explicitly optimized', prepared.eligibility(selected, native))

    def test_debug_rust_does_not_qualify_a_native_optimized_pair(self):
        selected, native = self.pair()
        selected['rust_compilation']['artifact']['profile']['debug_assertions'] = True
        self.assertTrue(any('Rust artifact is not an attested optimized' in item for item in prepared.eligibility(selected, native)))

    def test_matching_declared_profiles_clear_only_static_blockers(self):
        self.assertEqual(prepared.eligibility(*self.pair()), [])

    def test_backend_flags_may_differ_but_native_features_must_match(self):
        selected, native = self.pair()
        selected['inputs']['effective_configure'][-1:] = ['--with-swoole-rs={BUILD_PREFIX}', '--enable-swoole-rs-phpcollections']
        self.assertEqual(prepared.eligibility(selected, native), [])
        selected['inputs']['effective_configure'].remove('--enable-swoole-stdext')
        self.assertIn('Native configure options differ outside Rust backend selection', prepared.eligibility(selected, native))

    def test_php_sdk_mismatch_blocks_even_with_same_compiler_and_flags(self):
        selected, native = self.pair()
        native['inputs']['php_config'] = 'different SDK'
        self.assertIn('Native PHP/configuration identity missing or different: php_config', prepared.eligibility(selected, native))

    def test_two_null_php_identities_never_establish_a_matching_profile(self):
        selected, native = self.pair()
        for manifest in [selected, native]:
            manifest['inputs']['php_config'] = None
        self.assertIn('Native PHP/configuration identity missing or different: php_config', prepared.eligibility(selected, native))

    def observation(self, directory):
        (directory / 'Makefile').write_text('CXXFLAGS = -g -O2\n')
        (directory / 'config.h').write_text('#define TEST 1\n')
        (directory / 'build.log').write_text('libtool --mode=compile c++ -g -O2 -c facade.cc\n')
        (directory / 'build-manifest.json').write_text('{}')
        (directory / 'swoole.so').write_bytes(b'fixture')
        export = dict(native_compilation_observation=prepared.native_compilation(directory, directory / 'build.log'),
                      files={name: dict(sha256=prepared.sha(directory / name), bytes=(directory / name).stat().st_size)
                             for name in ['Makefile', 'config.h', 'build.log', 'build-manifest.json', 'swoole.so']})
        (directory / 'export.json').write_text(json.dumps(export))
        return directory / 'export.json'

    def test_postbuild_observation_recomputed_and_bound_to_actual_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            export = self.observation(directory)
            self.assertEqual(prepared.observed_flags(export, directory / 'build-manifest.json', directory / 'swoole.so'), '-g -O2')
            (directory / 'build.log').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'input changed'):
                prepared.observed_flags(export, directory / 'build-manifest.json', directory / 'swoole.so')

    def test_export_cannot_bind_a_different_actual_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            export = self.observation(directory)
            other = directory / 'other.so'
            other.write_bytes(b'other')
            with self.assertRaisesRegex(ValueError, 'does not identify'):
                prepared.observed_flags(export, directory / 'build-manifest.json', other)

    def test_missing_actual_commands_cannot_qualify_configured_optimization(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            export = self.observation(directory)
            data = json.loads(export.read_text())
            data['native_compilation_observation']['compile_command_count'] = 0
            export.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'retained commands'):
                prepared.observed_flags(export, directory / 'build-manifest.json', directory / 'swoole.so')

    def test_supplemental_correction_binds_exact_export_and_recomputed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            export = self.observation(directory)
            corrected = json.loads(export.read_text())['native_compilation_observation']
            original = json.loads(export.read_text())
            original['native_compilation_observation']['make_variables']['CC'] = 'historical parser error'
            export.write_text(json.dumps(original))
            correction = directory / 'correction.json'
            correction.write_text(json.dumps(dict(observations={'test': dict(export_sha256=prepared.sha(export), native_compilation_observation=corrected)})))
            self.assertEqual(prepared.observed_flags(export, directory / 'build-manifest.json', directory / 'swoole.so', correction), '-g -O2')
            export.write_text(export.read_text() + ' ')
            with self.assertRaisesRegex(ValueError, 'uniquely bind'):
                prepared.observed_flags(export, directory / 'build-manifest.json', directory / 'swoole.so', correction)

    @unittest.skipUnless(shutil.which('php'), 'actual PHP CLI is unavailable')
    def test_measurement_without_lease_token_refuses_before_extension_or_clocks(self):
        result = subprocess.run(['php', '-n', '-d', 'disable_functions=hrtime,microtime',
                                 str(Path(__file__).with_name('benchmark.php')), '--measure',
                                 'table-arithmetic', '100'], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('actual exclusive acknowledgment', result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
