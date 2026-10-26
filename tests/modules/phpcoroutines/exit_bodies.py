"""Both versioned exit frontends; Zend payloads/termination stay Native."""
SIGNATURES = ['static int coro_exit_handler(zend_execute_data *execute_data) {',
              'PHP_FUNCTION(swoole_exit) {']


