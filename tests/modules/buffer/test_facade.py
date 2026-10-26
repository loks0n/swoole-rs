"""Six seeded positive facade sequences, native versus the Buffer patches with Rust.

Binary data and CLOSE tokens, partial-consume offsets, CLOSE-token callbacks, stable
cached identity and mixed teardown. DATA destroy callbacks, DATA-token underflow and
unsafe vector/zero probes are out of scope.
"""
import subprocess

from native import native_and_selected
from tools.harness import ROOT


def test_facade(pinned, archive, pytestconfig):
    if pytestconfig.getoption('rust_asan'):
        assert pytestconfig.getoption('sanitize'), 'Rust ASan requires the native sanitizer runtime'
        probe = subprocess.run(['nm', '-u', str(archive)], capture_output=True, text=True)
        assert '__asan_report_' in probe.stdout, 'Supplied archive lacks Rust ASan report imports'
    tree = pinned('include', 'src/core/buffer.cc')
    outcomes = native_and_selected(tree, ROOT / 'tests/modules/buffer/model.cc', archive,
                                   pytestconfig.getoption('sanitize'), '-DMODEL_FACADE_ONLY', '-DMODEL_FACADE_CONTROL')
    for outcome in outcomes.values():
        assert (outcome['facade_sequences'], outcome['steps_per_sequence']) == (6, 64)
        assert outcome['passed'] and outcome['callbacks']
    assert outcomes['native'] == outcomes['selected']
