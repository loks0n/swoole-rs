"""Unchanged upstream String assertions and owned-storage behaviour, upstream against the
string-storage patch with Rust, one profile per consumer (see profiles.md)."""
import json
import subprocess

import pytest

from string_build import build, original_ids, pinned_tree
from tools.harness import ROOT, run_isolated

# profile: (consumer, Rust exports its callers reach, the outcome each engine must report).
# Other exports are linked only if a caller survives: since #392 inlined dispose,
# move/release is not always reachable.
PROFILES = {
    'originals': ('originals.cc', ['swr_v1_string_edit_in_place', 'swr_v1_string_append_in_place'], None),
    'split': ('split-continuation.cc', ['swr_v1_string_split_plan'], None),
    'integer': ('integers.cc', ['swr_v1_string_edit_object'], None),
    'ownership': ('ownership.cc', ['swr_v1_string_ownership_plan'], None),
    'allocation': ('allocation.cc', ['swr_v1_string_allocation_plan'], {'checks': 12}),
    'format': ('formatting.cc', ['swr_v1_string_format_step'], {'checks': 604}),
    'random': ('random.cc', ['swr_v1_string_random_step'], {'checks': 673}),
    'copy': ('copy.cc', ['swr_v1_string_transition'], None),
    'transitions': ('transitions.cc', ['swr_v1_string_transition'], None),
}


@pytest.mark.parametrize('profile', PROFILES)
def test_profile(tmp_path, archive, pytestconfig, profile):
    source = ROOT / 'target/upstream/src'
    if not (source / '.git').exists():
        pytest.skip('needs the pinned target/upstream/src')
    if pytestconfig.getoption('rust_asan'):
        assert pytestconfig.getoption('sanitize'), 'a Rust ASan archive needs the native sanitizer runtime'
        assert '__asan_report_' in subprocess.check_output(['nm', '-u', str(archive)], text=True)
    consumer, exports, expected = PROFILES[profile]
    tests = pinned_tree(source, tmp_path)
    ids = original_ids(tests)
    if profile == 'originals':
        assert len(ids) == 23
    for engine in ['upstream', 'rust']:
        binary = tmp_path / engine
        compiled = build(tmp_path, engine, consumer, binary, archive, sanitize=pytestconfig.getoption('sanitize'),
                         extra=[tests] if profile == 'originals' else [])
        assert compiled.returncode == 0, compiled.stderr
        if engine == 'rust':
            symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
            assert all(name in symbols for name in exports), exports
        result = run_isolated([str(binary)], timeout=30)
        assert result.returncode == 0, result.stderr
        outcome = json.loads(result.stdout.splitlines()[-1])
        if profile == 'originals':
            assert outcome.get('original_ids') == ids and outcome.get('failed') == 0, outcome
        elif profile == 'ownership':
            assert outcome == {'checks': 13, 'selected_origin_checks': 3 if engine == 'rust' else 0}
        elif expected:
            assert outcome == expected
