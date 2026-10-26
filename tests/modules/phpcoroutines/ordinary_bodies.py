"""Remaining ordinary stack/repeat arithmetic; Native pointers/effects retained."""
BOUNDS = ['void *PHPCoroutine::stack_limit(PHPContext *ctx) {', 'void *PHPCoroutine::stack_base(PHPContext *ctx) {']
KERNEL = 'PHP_FUNCTION(swoole_test_kernel_coroutine) {'


