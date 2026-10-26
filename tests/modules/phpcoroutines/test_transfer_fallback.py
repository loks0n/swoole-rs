"""Exact fallback and native memory-effect preservation for context transfers."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected
from transfer_bodies import SIGNATURES


class TransferFallback(unittest.TestCase):
    def test_original_effects_and_native_fallback(self):
        root = Path(__file__).resolve().parents[3]
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src'))
        path = pin / 'ext-src/swoole_coroutine.cc'
        if not path.exists():
            self.skipTest('Supply SWOOLE_UPSTREAM_SOURCE for pinned source')
        original = path.read_text()
        selected = coroutine_selected(original)
        for signature in SIGNATURES:
            before, after = body(original, signature), body(selected, signature)
            fallback = after.rsplit('#else\n', 1)[1].rsplit('#endif', 1)[0]
            self.assertEqual(fallback, before)
            self.assertIn('swr_coro_transfer_next(', after)
            # Every native write/copy/helper effect is carried verbatim; only
            # the surrounding presence/order policy crosses the Rust boundary.
            new_body = after.split('#else\n', 1)[0]
            for line in before.splitlines():
                if line.strip() and not line.lstrip().startswith(('if ', '} else', '} ', '}', '#')):
                    if any(field in line for field in ('ctx->tmp_error_reporting', 'ctx->ori_error_reporting')):
                        self.assertIn('swr_v1_phpcoroutines_metadata(', new_body)
                        self.assertIn('observation = EG(error_reporting);', new_body)
                        self.assertIn('EG(error_reporting) = static_cast<int>(part.value);', new_body)
                    else:
                        self.assertIn(line.strip(), new_body)


if __name__ == '__main__':
    unittest.main()
