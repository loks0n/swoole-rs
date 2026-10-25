"""Source-only closure: no PHP/callback/destructor/build or runtime execution."""
import os
from pathlib import Path
import tempfile
import unittest
from gate import body, stage

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', str(Path(__file__).resolve().parents[3] / 'target/upstream/src')))

def branches(function):
    """Select the outer feature guard, preserving inner Native capability guards."""
    marker = '\n#ifdef SWOOLE_RS_PHPEVENTS\n'
    start = function.index(marker) + len(marker)
    depth, position, fallback = 1, start, None
    for line in function[start:].splitlines(True):
        if line.startswith('#if'):
            depth += 1
        elif line.startswith('#else') and depth == 1:
            fallback = position
        elif line.startswith('#endif'):
            depth -= 1
            if depth == 0:
                if fallback is None:
                    raise ValueError('Missing original fallback')
                return function[start:fallback], function[fallback + len('#else'):position]
        position += len(line)
    raise ValueError('Unbalanced feature guard')


class CallbackSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        cls.native, cls.selected = stage(SOURCE, Path(cls.work.name))

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def test_relative_scratch_applies_real_overlay(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'target') as scratch:
            relative = Path(os.path.relpath(scratch, Path.cwd()))
            native, selected = stage(SOURCE, relative)
            self.assertNotEqual(native, selected)
            self.assertIn('swr_v1_phpevents_catalogue(index, 0', selected)
            self.assertIn('static zend_function_entry swoole_event_methods[12]{};', selected)

    def test_every_fallback_body_preserved(self):
        for signature in ['void php_swoole_event_wait() {',
                          'void php_swoole_event_exit() {',
                          'static PHP_FUNCTION(swoole_event_dispatch) {',
                          'static PHP_FUNCTION(swoole_event_rshutdown) {',
                          'int php_swoole_reactor_init() {',
                          'static void event_check_reactor() {',
                          'static void event_object_free(void *data) {',
                          'static PHP_FUNCTION(swoole_event_add) {',
                          'static PHP_FUNCTION(swoole_event_set) {',
                          'static int event_readable_callback(Reactor *reactor, Event *event) {',
                          'static int event_writable_callback(Reactor *reactor, Event *event) {']:
            original = body(self.native, signature)
            selected = body(self.selected, signature)
            _, fallback = branches(selected)
            self.assertEqual(fallback, original[original.index('{') + 1:-1])

    def test_whole_pair_layout_and_original_teardown_effects(self):
        struct = body(self.selected, 'struct EventObject {')
        self.assertIn('SwrPhpEventCallback readable_callback;', struct)
        self.assertIn('SwrPhpEventCallback writable_callback;', struct)
        for name in ['zsocket', 'readable_callback', 'writable_callback']:
            self.assertIn('offsetof(EventObject, ' + name + ') == offsetof(EventObjectNativeLayout, ' + name + ')', self.selected)
        free = body(self.selected, 'static void event_object_free(void *data) {').split('\n#else')[0]
        self.assertIn('delete reinterpret_cast<zend::Callable *>(identity);', free)
        self.assertLess(free.index('swr_v1_phpevents_callbacks'), free.index('delete reinterpret_cast'))
        self.assertLess(free.index('zval_ptr_dtor'), free.index('efree(peo)'))
        self.assertNotIn('nullptr', free)
        self.assertNotIn('swr_', free[free.index('efree(peo)'):])

    def test_complete_admission_caller_lazy_reads_and_effects(self):
        admission = body(self.selected, 'int php_swoole_reactor_init() {').split('\n#else')[0]
        for effect in ['SWOOLE_G(cli)', 'sw_server()->is_task_worker()',
                       'sw_server()->task_enable_coroutine', 'sw_server()->is_manager()',
                       'swoole_event_init(SW_EVENTLOOP_WAIT_EXIT)',
                       'php_swoole_register_shutdown_function("swoole_event_rshutdown")',
                       'isset_exit_condition', 'set_exit_condition']:
            self.assertIn(effect, admission)
        self.assertIn('swr_v1_phpevents_reactor_init', admission)
        handlers = body(self.selected, 'static void event_check_reactor() {').split('\n#else')[0]
        self.assertLess(handlers.index('SW_EVENT_READ, event_readable_callback'), handlers.index('SW_EVENT_WRITE, event_writable_callback'))
        self.assertLess(handlers.index('SW_EVENT_WRITE, event_writable_callback'), handlers.index('SW_EVENT_ERROR, event_error_callback'))
        self.assertIn('swr_v1_phpevents_handlers', handlers)

    def test_native_bailout_and_optional_flag_boundaries_preserved(self):
        wait, _ = branches(body(self.selected, 'void php_swoole_event_wait() {'))
        self.assertIn('#if defined(EG_FLAGS_IN_SHUTDOWN) && !defined(EG_FLAGS_OBJECT_STORE_NO_REUSE)', wait)
        self.assertIn('EG(flags) &= ~EG_FLAGS_IN_SHUTDOWN;', wait)
        self.assertIn('EG(flags) |= EG_FLAGS_IN_SHUTDOWN;', wait)
        shutdown = body(self.selected, 'static PHP_FUNCTION(swoole_event_rshutdown) {').split('\n#else')[0]
        self.assertLess(shutdown.index('zend_try'), shutdown.index('swr_v1_phpevents_loop'))
        self.assertLess(shutdown.index('swr_v1_phpevents_loop'), shutdown.index('php_swoole_event_wait();'))
        self.assertIn('zend_end_try();', shutdown)

    def test_complete_callers_no_selected_native_slot_policy(self):
        update = body(self.selected, 'static PHP_FUNCTION(swoole_event_set) {').split('\n#else')[0]
        self.assertIn('swr_v1_phpevents_update_owned', update)
        self.assertEqual(update.count('swoole_event_defer(sw_callable_free, reinterpret_cast<void *>(identity))'), 2)
        self.assertNotIn('peo->readable_callback =', update)
        self.assertNotIn('peo->writable_callback =', update)
        for category in ('readable', 'writable'):
            selected = body(self.selected, 'static int event_' + category + '_callback(Reactor *reactor, Event *event) {').split('\n#else')[0]
            self.assertIn('swr_v1_phpevents_callbacks', selected)
            self.assertLess(selected.index('swr_v1_phpevents_callbacks'), selected.index('->ptr()'))
            self.assertNotIn('peo->' + category + '_callback->', selected)

if __name__ == '__main__':
    unittest.main()
