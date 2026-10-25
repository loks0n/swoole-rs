import unittest
from stats_runtime import (QUERY_BINDING_MARKER, QUERY_HEADER_MARKERS, QUERY_OLD_ACTIVE,
                           ACTIVATED_HEADER_MARKERS, ACTIVATED_CPP_MARKERS, METADATA_HEADER_MARKERS, validate_queries_projection)


class QueriesIdentity(unittest.TestCase):
    def test_real_common_and_binding_callers_required(self):
        manifest = {'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/context.rs': 'qualified'}}}
        validate_queries_projection(manifest, QUERY_BINDING_MARKER, b'\n'.join(QUERY_HEADER_MARKERS), 'qualified')
        with self.assertRaises(ValueError):
            validate_queries_projection(manifest, b'original native query body', b'\n'.join(QUERY_HEADER_MARKERS), 'qualified')
        for index in range(len(QUERY_HEADER_MARKERS)):
            with self.assertRaises(ValueError):
                validate_queries_projection(manifest, QUERY_BINDING_MARKER,
                    b'\n'.join(QUERY_HEADER_MARKERS[:index] + QUERY_HEADER_MARKERS[index+1:]), 'qualified')

    def test_old_module_bit_or_changed_source_rejected(self):
        for digest in (None, 'different'):
            sources = {} if digest is None else {'crates/phpcoroutines/src/context.rs': digest}
            with self.assertRaises(ValueError):
                validate_queries_projection({'inputs': {'rust_sources_sha256': sources}}, QUERY_BINDING_MARKER,
                    b'\n'.join(QUERY_HEADER_MARKERS), 'qualified')

    def test_new_custody_requires_actual_phase_source_and_callers(self):
        manifest = {'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/context.rs': 'qualified',
                    'crates/phpcoroutines/src/scheduler_phase.rs': 'phase-qualified'}}}
        header = b'\n'.join([x for x in QUERY_HEADER_MARKERS if x != QUERY_OLD_ACTIVE] + ACTIVATED_HEADER_MARKERS)
        patch = b'\n'.join([QUERY_BINDING_MARKER] + ACTIVATED_CPP_MARKERS)
        validate_queries_projection(manifest, patch, header, 'qualified', 'phase-qualified')
        for phase in (None, 'wrong'):
            with self.assertRaises(ValueError):
                validate_queries_projection(manifest, patch, header, 'qualified', phase)
        with self.assertRaises(ValueError):
            # A new typed slot cannot borrow legacy marker acceptance to omit
            # its new compiled Rust phase identity/publications.
            validate_queries_projection(manifest, QUERY_BINDING_MARKER,
                b'\n'.join(QUERY_HEADER_MARKERS + [ACTIVATED_HEADER_MARKERS[0]]), 'qualified')
        for marker in ACTIVATED_CPP_MARKERS + ACTIVATED_HEADER_MARKERS:
            with self.assertRaises(ValueError):
                validate_queries_projection(manifest, patch.replace(marker, b'old'), header.replace(marker, b'old'),
                                            'qualified', 'phase-qualified')

    def test_new_context_cells_require_source_and_whole_idle_callers(self):
        manifest = {'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/context.rs': 'qualified',
                    'crates/phpcoroutines/src/scheduler_phase.rs': 'phase-qualified',
                    'crates/phpcoroutines/src/context_metadata.rs': 'cells-qualified'}}}
        header = b'\n'.join([QUERY_HEADER_MARKERS[0]] + ACTIVATED_HEADER_MARKERS + METADATA_HEADER_MARKERS)
        patch = b'\n'.join([QUERY_BINDING_MARKER] + ACTIVATED_CPP_MARKERS)
        validate_queries_projection(manifest, patch, header, 'qualified', 'phase-qualified', 'cells-qualified')
        for digest in (None, 'wrong'):
            with self.assertRaises(ValueError):
                validate_queries_projection(manifest, patch, header, 'qualified', 'phase-qualified', digest)
        for marker in METADATA_HEADER_MARKERS:
            with self.assertRaises(ValueError):
                validate_queries_projection(manifest, patch, header.replace(marker, b'old'), 'qualified', 'phase-qualified', 'cells-qualified')


if __name__ == '__main__':
    unittest.main()
