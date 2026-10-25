"""Timer callback and captured-object destructor exit/exception/OOM teardown.

Every engine must produce a valid teardown and exactly the control's exit code,
stdout and stderr. A control that times out or fails fails every comparison;
no candidate is ever promoted to control. No original PHPT is changed.
"""
import functools
from pathlib import Path

import pytest

from tools.harness import run_isolated

HERE = Path(__file__).parent


@functools.cache
def observe(command):
    result = run_isolated(list(command), timeout=5)
    return result.returncode, result.stdout, result.stderr


def compare(engine, control, *arguments):
    assert observe(tuple(engine.command(*arguments))) == observe(tuple(control.command(*arguments))), 'differs from control'


# Exit and converted exceptions can return to the native loop; always clear
# them. Fatal OOM must also preserve uncleared state.
@pytest.mark.parametrize('mode,clear', [('exit', 1), ('throw', 1), ('oom', 1), ('oom', 0)])
@pytest.mark.parametrize('coroutine', [0, 1])
@pytest.mark.parametrize('kind', ['after', 'tick'])
def test_callback(engine, control, kind, coroutine, mode, clear):
    arguments = ('-d', 'memory_limit=-1', HERE / 'bailout.php', kind, mode, coroutine, clear)
    returncode, stdout, stderr = observe(tuple(engine.command(*arguments)))
    assert returncode >= 0 and stdout.count('CALL\n') == 1 and stdout.count('SHUTDOWN ') == 1 and 'STATE ' in stdout
    if mode == 'oom':
        assert returncode == 255 and 'SHUTDOWN 1\n' in stdout and 'Allowed memory size' in stdout + stderr
    compare(engine, control, *arguments)


# after/tick: destructor after a successful callback. clear/clear-all: idle
# clear outside active selection. event-exit-*: Event::exit clears other timers.
@pytest.mark.parametrize('mode', ['exit', 'throw', 'oom'])
@pytest.mark.parametrize('coroutine', [0, 1])
@pytest.mark.parametrize('kind', ['after', 'tick', 'clear', 'clear-all', 'event-exit-after', 'event-exit-tick'])
def test_destructor(engine, control, kind, coroutine, mode):
    callback = kind in ('after', 'tick')
    fixture = HERE / ('destructor_bailout.php' if callback else 'destructor_clear.php')
    arguments = ('-d', 'display_errors=stderr', fixture, kind, coroutine, mode)
    returncode, stdout, stderr = observe(tuple(engine.command(*arguments)))
    assert (returncode >= 0 and stdout.count('CALL\n') == int(callback)
            and stdout.count('DTOR\n') == 1 and stdout.count('SHUTDOWN\n') == 1)
    if mode == 'oom':
        assert returncode == 255 and 'Allowed memory size' in stdout + stderr
    compare(engine, control, *arguments)
