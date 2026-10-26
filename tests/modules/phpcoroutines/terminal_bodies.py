"""Terminal/diagnostic decisions only; all Native effects execute after Rust returns."""
SIGNATURES = ['bool PHPCoroutine::catch_exception() {',
              'void PHPCoroutine::deadlock_check() {',
              'void PHPCoroutine::on_close(void *arg) {']


