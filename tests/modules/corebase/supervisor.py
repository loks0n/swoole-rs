"""Run Python supervisors in-process so leaf harness cleanup can unwind."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import os
from pathlib import Path
import runpy
import signal
import sys
import traceback


@contextmanager
def cooperative_signals():
    def cancel(signum, frame):
        raise KeyboardInterrupt('cancelled by signal ' + str(signum))
    previous = {sig: signal.getsignal(sig) for sig in [signal.SIGTERM, signal.SIGINT]}
    for sig in previous:
        signal.signal(sig, cancel)
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def run_tool(command, log, cwd, env=None):
    """No outer timeout/session: child tools bound and clean their leaf groups.

    TERM/INT must unwind the active leaf harness before a caller force-kills this
    supervisor. SIGKILL cannot execute Python cleanup. Never report it as proven.
    """
    command = list(map(str, command))
    previous_argv, previous_cwd, previous_env = sys.argv, Path.cwd(), os.environ.copy()
    with Path(log).open('w') as output, redirect_stdout(output), redirect_stderr(output):
        try:
            if env is not None:
                os.environ.clear(); os.environ.update(env)
            sys.argv = command[1:]
            os.chdir(cwd)
            with cooperative_signals():
                runpy.run_path(command[1], run_name='__main__')
            return 0
        except SystemExit as error:
            if error.code is None:
                return 0
            if isinstance(error.code, int):
                return error.code
            print(error.code, file=sys.stderr)
            return 1
        except BaseException:
            traceback.print_exc()
            raise
        finally:
            sys.argv = previous_argv
            os.chdir(previous_cwd)
            os.environ.clear(); os.environ.update(previous_env)
