"""Source-only sole join metadata; no actual join/context/callback execution."""
import os
from pathlib import Path
import unittest
from make_patches import body, coroutine_selected
from join_bodies import OWNER, SIGNATURE


class JoinBoundary(unittest.TestCase):
    def test_original_native_payloads_publication_and_error_branches(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not pin.exists():
            self.skipTest('Supply pinned source')
        source = pin.read_text(); selected = coroutine_selected(source)
        before, after = body(source, SIGNATURE), body(selected, SIGNATURE)
        suffix = '#else' + before + '#endif\n'
        self.assertTrue(after.endswith(suffix))
        active = after[:-len(suffix)]
        self.assertIn(OWNER, selected)
        for text in ['co_set', 'shared_ptr', 'make_shared', '*canceled']:
            self.assertNotIn(text, active)
        for statement in ['Coroutine *co = Coroutine::get_current_safe();', 'if (php_swoole_array_length(cid_array) == 0) {',
                          'if (co->get_cid() == cid) {', 'auto ctx = PHPCoroutine::get_context_by_cid(cid);',
                          'if (ctx == nullptr) {', 'if (ctx->on_close) {', 'ctx->on_close = &join_fn;',
                          'if (!co->yield_ex(timeout)) {', 'co->resume();', 'ctx->on_close = nullptr;']:
            self.assertEqual(active.count(statement), before.count(statement))
        for statement in ['swoole_set_last_error(SW_ERROR_INVALID_PARAMS);', 'swoole_set_last_error(SW_ERROR_WRONG_OPERATION);',
                          'php_swoole_error_ex(E_WARNING, SW_ERROR_WRONG_OPERATION, "can not join self");']:
            self.assertEqual(active.count(statement), before.count(statement))
        self.assertIn('[metadata, co](PHPContext *task)', active)
        self.assertIn('[co, metadata](void *)', active)
        self.assertLess(active.index('ctx->on_close = &join_fn;'), active.index('metadata.insert('))
        self.assertLess(active.index('ctx->on_close = nullptr;'), active.index('metadata.cancel();'))
        self.assertIn('reinterpret_cast<PHPContext *>(token)', active)
        self.assertIn('metadata.erase_empty(reinterpret_cast<uintptr_t>(task))', active)
        self.assertIn('if (metadata.can_resume())', active)
        self.assertLess(active.index('PHPCoroutineJoinMembership membership;'), active.index('PHPCoroutineJoinMetadata metadata;'))
        self.assertLess(active.index('membership.bind(metadata);'), active.index('PHPContext::SwapCallback join_fn'))
        self.assertLess(OWNER.index('swr_v1_phpcoroutines_join_release_membership(owner);'), OWNER.rindex('swr_v1_phpcoroutines_join_drop(owner);'))
        # Insertion/order state and shared flag/refcount exist only in Rust.
        self.assertNotIn('std::set', OWNER)
        self.assertNotIn('bool canceled', OWNER)


if __name__ == '__main__':
    unittest.main()
