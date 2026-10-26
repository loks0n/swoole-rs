"""Cancellation/timeout frontend ordering; all Native Zend/core/timer effects stay Native."""
SIGNATURES = ['static bool php_swoole_coroutine_throw_exception(long cid, bool throw_exception, zend_class_entry *ce) {',
              'static PHP_METHOD(swoole_coroutine, setTimeLimit) {']


