"""Compiler/engine-free source, real caller closure and origin refusals."""
import hashlib
import unittest
import output_workflow_identity as identity


class OutputWorkflowIdentity(unittest.TestCase):
    def fixture(self):
        source = b'pub fn '+identity.SYMBOL.encode()+b'() {}'
        patch = '\n'.join('+ auto reply = '+identity.SYMBOL+'(&state, '+str(op)+', observed, LIMIT);' for op in range(3)).encode()
        inputs = {'rust_sources_sha256': {identity.SOURCE: hashlib.sha256(source).hexdigest()},
                  'patches': [{'path': identity.PATCH, 'sha256': hashlib.sha256(patch).hexdigest()}]}
        return inputs, source, patch

    def test_source_and_each_caller_must_match(self):
        inputs, source, patch = self.fixture()
        self.assertEqual(identity.prepared(inputs, source, patch)['caller_operations'], [0, 1, 2])
        for args in [({}, source, patch), (inputs, source+b'changed', patch), (inputs, source, patch+b'changed')]:
            with self.subTest(args=args[0]), self.assertRaises(ValueError):identity.prepared(*args)

    def test_missing_caller_export_or_repeated_overlay_refuses(self):
        for remove_export, remove_caller, repeated in [(True, False, False), (False, True, False), (False, False, True)]:
            inputs, source, patch = self.fixture()
            if remove_export:source = b'no export'
            if remove_caller:patch = patch.splitlines()[0]
            inputs['rust_sources_sha256'][identity.SOURCE] = hashlib.sha256(source).hexdigest()
            inputs['patches'][0]['sha256'] = hashlib.sha256(patch).hexdigest()
            if repeated:inputs['patches'] *= 2
            with self.assertRaises(ValueError):identity.prepared(inputs, source, patch)

    def test_comments_do_not_count_as_call_expressions(self):
        inputs, source, patch = self.fixture()
        patch = patch.replace(b'+ auto reply', b'+ // auto reply')
        inputs['patches'][0]['sha256'] = hashlib.sha256(patch).hexdigest()
        with self.assertRaises(ValueError):identity.prepared(inputs, source, patch)

    def test_actual_selected_origin_and_native_absence(self):
        identity.consumer({'workflow_policy_image': '/selected.so'}, '/selected.so', True)
        identity.consumer({'workflow_policy_image': None}, '/native.so', False)
        for result, selected in [({}, True), ({'workflow_policy_image': '/other.so'}, True), ({'workflow_policy_image': '/selected.so'}, False)]:
            with self.assertRaises(ValueError):identity.consumer(result, '/selected.so', selected)


if __name__ == '__main__':unittest.main()
