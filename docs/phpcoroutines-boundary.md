# PHP coroutine frontend boundary (M29)

Feature value 134217728 (`--module phpcoroutines`, `SWOOLE_RS_PHPCOROUTINES`).
Upstream targets: `ext-src/swoole_coroutine.cc`,
`ext-src/swoole_coroutine_system.cc`, `ext-src/swoole_coroutine_scheduler.cc`,
`ext-src/php_swoole_coroutine.h`, `ext-src/swoole_tracer.cc`. Public headers,
arginfo, stubs and `PHPContext` layout are unchanged. Follows the
[policy/effect split](abi-v1.md#policyeffect-split).

Scope: frontend API catalog, argument/control/result policy, System
option/path/family/timeout policy, Scheduler configuration and task ordering.
Zend values, callbacks, refcounts, GC, exceptions, bailout, context/fiber/thread
switches, interruption, yield/resume and filesystem/DNS/process/signal/IO effects
stay native.

Implemented:

- **Scheduler**: queue, ordering and signed count storage are in Rust, with the
  real `add`/`parallel`/`start`/free callers, over four C exports.
- **Configuration**: `PHPCoroutine::config` is one inline `repr(C)` value under
  the original `SW_THREAD_LOCAL` scope (or the global fallback), initialized only
  from the compile-time default (`preemptive=false`, `deadlock=true`). No dynamic
  initializer, Rust TLS, heap, destructor or lock. Accessors `get_max_num`,
  `set_max_num`, `set_deadlock_check`, `get_hook_flags` and
  `enable_preemptive_scheduler` use it. Public `Config`'s four fields and all
  signatures are unchanged; the static's type changes, so rebuild the SDK.
- **Activation**: `activated` and `is_activated()` are a Rust-managed inline byte with the same TLS/global initialization.

Other Coroutine and System bodies are still C++. Original inventory: 130 Coroutine,
18 System and 27 Scheduler PHPTs.
