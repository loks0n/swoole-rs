"""Source-only real System caller custody; no process/signal/IPC/IO execution."""
import os
from pathlib import Path
import unittest
from overlay import body, system_selected
from system_control_bodies import SIGNATURES


class SystemControlBoundary(unittest.TestCase):
    def test_native_parse_storage_effects_and_error_observation_points(self):
        root = Path(__file__).resolve().parents[3]
        path = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src')) / 'ext-src/swoole_coroutine_system.cc'
        if not path.exists():
            self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        original = path.read_text()
        selected = system_selected(original)
        markers = ['    if (!System::exec(', '    if (pid < 0) {',
                   '    if (signo == -1) {', '    if (fd < 0) {']
        for signature, marker in zip(SIGNATURES, markers):
            before = body(original, signature)
            after = body(selected, signature).split('#else', 1)[0]
            self.assertIn(before[:before.index(marker)], after)
            self.assertIn('swr_v1_phpcoroutines_system_complete(', after)
        before = body(original, SIGNATURES[0])
        custody = before[before.index('    auto str ='):before.index('    array_init(return_value);')]
        self.assertIn(custody, body(selected, SIGNATURES[0]))
        for signature in SIGNATURES[:2]:
            after = body(selected, signature).split('#else', 1)[0]
            self.assertEqual(after.count('WEXITSTATUS(status)'), 1)
            self.assertEqual(after.count('WTERMSIG(status)'), 1)
        signal = body(selected, SIGNATURES[2]).split('#else', 1)[0]
        for statement in ['swoole_get_last_error() == EBUSY',
                          'swoole_get_last_error() == EINVAL',
                          'errno = swoole_get_last_error();',
                          'php_swoole_fatal_error(E_WARNING, "Unable to wait signal, async signal listener has been registered");',
                          'php_swoole_fatal_error(E_WARNING, "Invalid signal in the given list");']:
            self.assertEqual(signal.count(statement), 1)
        self.assertEqual(signal.count('swoole_get_last_error()'), 3)
        event = body(selected, SIGNATURES[3]).split('#else', 1)[0]
        self.assertEqual(event.count('System::wait_event(fd, events, timeout)'), 1)


if __name__ == '__main__':
    unittest.main()
