"""Actual startup proof requires compiled source and all three real callers."""
import unittest
from stats_runtime import validate_startup_projection


class StartupIdentity(unittest.TestCase):
    def setUp(self):
        self.manifest = {'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/bootstrap.rs': 'qualified'}}}
        self.patches = [('+        const auto plan = swr_v1_phpcoroutines_bootstrap(&state, '
                         + str(kind) + ', observation, exit_opcode);').encode() for kind in range(3)]

    def test_requires_qualified_rust_source(self):
        validate_startup_projection(self.manifest, self.patches, 'qualified')
        with self.assertRaises(ValueError):
            validate_startup_projection(self.manifest, self.patches, 'different')

    def test_requires_each_actual_native_caller(self):
        with self.assertRaises(ValueError):
            validate_startup_projection(self.manifest, self.patches[:2], 'qualified')
        for kind in range(3):
            patches = self.patches.copy()
            patches[kind] = b'old native MINIT'
            with self.assertRaises(ValueError):
                validate_startup_projection(self.manifest, patches, 'qualified')


class MethodStartupIdentity(unittest.TestCase):
    def test_requires_compiled_catalogue_and_all_stable_tables_and_callers(self):
        from stats_runtime import METHOD_PROJECTION_MARKER, METHOD_TABLES
        manifest = {'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/bootstrap.rs':'boot',
                    'crates/phpcoroutines/src/method_catalogue.rs':'methods'}}}
        patches = []
        for frontend, tables in enumerate(METHOD_TABLES):
            # Synthetic attestation members only; no Native/PHP execution.
            rows = [('+        const auto plan = swr_v1_phpcoroutines_bootstrap(&state, ' + str(frontend) + ', observation, exit_opcode);').encode(), METHOD_PROJECTION_MARKER]
            for kind, table, capacity in tables:
                rows += [f'+static zend_function_entry {table}[{capacity}]{{}};'.encode(),
                         f'+            php_coroutine_project_methods({kind}, {table}_bindings, {table});'.encode()]
            patches.append(b'\n'.join(rows))
        validate_startup_projection(manifest,patches,'boot','methods')
        for digest in (None, 'old'):
            with self.assertRaises(ValueError):validate_startup_projection(manifest,patches,'boot',digest)
        for i, patch in enumerate(patches):
            for row in patch.splitlines()[1:]:
                changed = patches.copy(); changed[i] = patch.replace(row,b'')
                with self.assertRaises(ValueError):validate_startup_projection(manifest,changed,'boot','methods')


if __name__ == '__main__':
    unittest.main()
