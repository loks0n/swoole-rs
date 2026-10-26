"""Request/creation lifecycle policy; native Zend/callback/bailout effects retained."""
SIGNATURES = ['PHP_FUNCTION(swoole_coroutine_create) {',
              'void php_swoole_coroutine_rshutdown() {',
              'void PHPCoroutine::bailout() {']


