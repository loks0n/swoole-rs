"""Fiber observer policy; original native reads/effects and fallback stay native."""
SIGNATURES = ['zend_fiber_status PHPCoroutine::fiber_get_status(const PHPContext *ctx) {',
    'void PHPCoroutine::fiber_context_switch_notify(const PHPContext *from, PHPContext *to) {',
    'void PHPCoroutine::fiber_context_switch_try_notify(const PHPContext *from, PHPContext *to) {',
    'void PHPCoroutine::fiber_context_try_destroy(const PHPContext *ctx, PHPContext *origin_ctx) {']


