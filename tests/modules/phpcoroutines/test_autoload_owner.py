"""Account exact Native effects around the selected sole autoload metadata owner."""
import os
from pathlib import Path
import unittest

from make_patches import body, coroutine_selected


class AutoloadOwnerBoundary(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('SWOOLE_UPSTREAM_SOURCE'), 'pinned source required')
    def test_complete_owner_uses_one_rust_handle_and_preserves_effect_order(self):
        source = (Path(os.environ['SWOOLE_UPSTREAM_SOURCE']) / 'ext-src/swoole_coroutine.cc').read_text()
        selected = coroutine_selected(source)
        signature = 'static zend_class_entry *swoole_coroutine_autoload(zend_string *name, zend_string *lc_name) {'
        original = body(source, signature)
        routed = body(selected, signature)
        self.assertIn('#else\n' + original, routed)
        selected_body = routed.split('#else\n', 1)[0]
        self.assertNotIn('AutoloadQueue queue;', selected_body)
        self.assertNotIn('pending_queue->coroutine', selected_body)
        self.assertNotIn('pending_queue->queue', selected_body)
        self.assertIn('observation = pending_queue->is_owner(current);', selected_body)
        self.assertIn('pending_queue->push(&context);\n            current->yield();\n            return context.ce;', selected_body)
        owner = selected_body[selected_body.index('    AutoloadContextQueue queue_object(current);'):]
        effects = [
            'zend_hash_add_ptr(SWOOLE_G(in_autoload), lc_name, &queue_object);',
            'zend_class_entry *ce = original_zend_autoload(name, lc_name);',
            'zend_hash_del(SWOOLE_G(in_autoload), lc_name);',
            'while (queue_object.pop(&pending_context)) {',
            'pending_context->ce = ce;',
            'pending_context->coroutine->resume();',
            'return ce;',
        ]
        positions = [owner.index(effect) for effect in effects]
        self.assertEqual(positions, sorted(positions))
        wrapper = selected[selected.index('class AutoloadContextQueue {'):selected.index('static zend_class_entry *swoole_coroutine_autoload')]
        self.assertEqual(wrapper.count('swr_phpcoroutines_autoload_queue *queue;'), 1)
        self.assertIn('swr_v1_phpcoroutines_autoload_owner_try_new(reinterpret_cast<uintptr_t>(owner))', wrapper)
        self.assertIn('~AutoloadContextQueue() { swr_v1_phpcoroutines_autoload_drop(queue); }', wrapper)
        self.assertNotIn('Coroutine *coroutine;', wrapper.split('#else', 1)[0])
