"""Whole pinned timer PHPT inventory; original assertions and official runner.

Each engine gets fresh disposable support files and runs every case serially in
isolation. Four route/DNS-dependent cases run only with --external-network.
"""
import hashlib
from pathlib import Path
import socket
import subprocess

import pytest

from corpus.upstream.run import COMMIT, prepare, run_cases
from tools.harness import ROOT

SOURCE = ROOT / 'target/upstream/src'
EXTERNAL = {'bug_4794_3', 'bug_4794_5', 'bug_4794_6', 'bug_4794_7'}


def selection(source, external=False, names=()):
    pin = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if pin != COMMIT:
        raise ValueError('Timer source HEAD differs from frozen pin')
    paths = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', '--name-only', COMMIT,
                                    'tests/swoole_timer'], text=True).splitlines()
    paths = sorted(path for path in paths if path.endswith('.phpt'))
    if len(paths) != 33 or not EXTERNAL <= {Path(path).stem for path in paths}:
        raise ValueError('Pinned 33-case timer inventory differs; review selection')
    if set(names) - {Path(path).stem for path in paths}:
        raise ValueError('Unknown timer --case name')
    selected, unmeasured = [], []
    for path in paths:
        name = Path(path).stem
        if names and name not in names or name in EXTERNAL and not external:
            unmeasured.append(path)
            continue
        original = subprocess.check_output(['git', '-C', str(source), 'show', f'{COMMIT}:{path}'])
        selected.append({'path': path, 'module': 'timers', 'sha256': hashlib.sha256(original).hexdigest()})
    if not selected:
        raise ValueError('No timer cases selected; external cases require --external-network')
    return selected, unmeasured


def require_free_port(port=9601):
    # Match reusable listeners without rejecting a prior engine's closed socket
    # still in TCP TIME_WAIT. A live listener on this address remains an error.
    with socket.socket() as guard:
        guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        guard.bind(('127.0.0.1', port))


def pytest_generate_tests(metafunc):
    if 'case' in metafunc.fixturenames:
        cases = selection(SOURCE, metafunc.config.getoption('external_network'))[0] if 'engine' in metafunc.fixturenames and metafunc.config.getoption('engine') else []
        metafunc.parametrize('case', cases, ids=[Path(case['path']).stem for case in cases])


@pytest.fixture(scope='module')
def sandbox(pytestconfig, tmp_path_factory):
    cases = selection(SOURCE, pytestconfig.getoption('external_network'))[0]
    made = {}

    def get(engine):
        if engine.name not in made:
            path = made[engine.name] = tmp_path_factory.mktemp('timer-original-' + engine.name)
            prepare(SOURCE, path, cases)
            (path / 'home').mkdir()
            (path / 'tmp').mkdir()
        return made[engine.name]
    return get


def test_original(engine, case, sandbox, tmp_path, pytestconfig):
    if Path(case['path']).stem == 'bug_4794_8':
        require_free_port()
    results, _ = run_cases(engine, [case], sandbox(engine), tmp_path, 30, 1,
                           offline=not pytestconfig.getoption('external_network'))
    result = results[case['path']]
    assert result['status'] == 'passed', result.get('detail')


class Fixture:
    def __init__(self):
        self.names = sorted(EXTERNAL) + [f'local_{number:02}' for number in range(29)]
        self.paths = [f'tests/swoole_timer/{name}.phpt' for name in self.names]

    def __call__(self, args, **kwargs):
        if 'rev-parse' in args:
            return COMMIT
        if 'ls-tree' in args:
            return '\n'.join(self.paths)
        return b'--FILE--\noriginal assertions\n'


@pytest.fixture
def git(monkeypatch):
    fixture = Fixture()
    monkeypatch.setattr(subprocess, 'check_output', fixture)
    return fixture


def test_local_gate_accounts_for_all_four_unmeasured_cases(git):
    cases, omitted = selection(Path('fixture'))
    assert len(cases) == 29
    assert {Path(path).stem for path in omitted} == EXTERNAL
    assert cases[0]['sha256'] == hashlib.sha256(git([])).hexdigest()


def test_external_cases_require_explicit_network_selection(git):
    cases, omitted = selection(Path('fixture'), external=True)
    assert (len(cases), omitted) == (33, [])
    with pytest.raises(ValueError, match='external cases require'):
        selection(Path('fixture'), names=['bug_4794_3'])


def test_fixed_port_guard_refuses_live_listener():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(OSError):
            require_free_port(port)
    require_free_port(port)


def test_unknown_names_wrong_pin_and_incomplete_inventory_fail(git, monkeypatch):
    with pytest.raises(ValueError, match='Unknown'):
        selection(Path('fixture'), names=['not_original'])
    git.paths.pop()
    with pytest.raises(ValueError, match='33-case'):
        selection(Path('fixture'))
    monkeypatch.setattr(subprocess, 'check_output', lambda *args, **kwargs: 'wrong-pin')
    with pytest.raises(ValueError, match='frozen pin'):
        selection(Path('fixture'))
