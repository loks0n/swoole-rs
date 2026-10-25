"""Source and origin requirements for the unchanged9/78 output consumer."""
import hashlib
import re

SOURCE = 'crates/reactor/src/output_workflow.rs'
PATCH = 'migration/patches/reactor/0004-socket-output.patch'
SYMBOL = 'swr_v1_reactor_output_workflow'


def prepared(inputs, source, patch):
    if inputs.get('rust_sources_sha256', {}).get(SOURCE) != hashlib.sha256(source).hexdigest():
        raise ValueError('Selected source predates/mismatches complete output workflow')
    matches = [entry for entry in inputs.get('patches', []) if entry.get('path') == PATCH]
    if len(matches) != 1 or matches[0].get('sha256') != hashlib.sha256(patch).hexdigest():
        raise ValueError('Selected output caller overlay identity differs')
    if ('fn '+SYMBOL+'(').encode() not in source:
        raise ValueError('Typed output workflow export missing')
    calls = re.findall(r'^\+\s*auto reply = '+re.escape(SYMBOL)+r'\(&state, ([012]), [^;]+\);$',
                       patch.decode(), re.MULTILINE)
    if sorted(calls) != ['0', '1', '2']:
        raise ValueError('Require all three actual output workflow caller bodies')
    return {'source': SOURCE, 'source_sha256': hashlib.sha256(source).hexdigest(),
            'caller_patch': PATCH, 'caller_patch_sha256': hashlib.sha256(patch).hexdigest(),
            'caller_operations': [0, 1, 2]}


def consumer(result, extension, selected):
    if result.get('workflow_policy_image') != (extension if selected else None):
        raise ValueError('Actual output workflow origin differs from selected/Native control')
