"""Select complete context-transfer ordering without interpreting Zend memory."""

SIGNATURES = [f'{prefix}void PHPCoroutine::{name}(PHPContext *ctx) {{'
              for prefix, name in [('inline ', 'save_vm_stack'), ('inline ', 'restore_vm_stack'),
                                   ('inline ', 'save_og'), ('inline ', 'restore_og'),
                                   ('', 'save_bg'), ('', 'restore_bg'),
                                   ('', 'save_context'), ('', 'restore_context')]]
NOTIFICATION_SIGNATURES = ['void PHPCoroutine::on_yield(void *arg) {',
                           'void PHPCoroutine::on_resume(void *arg) {']


