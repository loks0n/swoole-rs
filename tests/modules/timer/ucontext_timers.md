# Native ucontext timer custody

`core.py --ucontext-timers` builds the original and timer-only native libraries
with ucontext coroutines (undefining `SW_USE_ASM_CONTEXT` in private config
copies; a thread-context config is rejected) and runs `ucontext_timers.cc`
against each. It also requires actual `getcontext`/`makecontext`/`swapcontext`
imports in each built `libswoole.so`. Linux only, as part of the
[core GoogleTest gate](UPSTREAM.md#original-native-googletest-gate).

The fixture uses the real native coroutine stack:

- resumes from timer expiry and observes the timeout error;
- resumes from cancellation with the later expiry timer removed by `yield_ex`;
- suspends while a repeating timer runs three times, removes that active node
  before its synchronous resumption, then continues on the owner thread;
- resumes once more and finishes inside a one-shot callback.

Final timer and coroutine counts must be zero. Linux original and timer-only
builds both pass, alongside the nine original timer tests per library.

## Not covered

- macOS ucontext, sanitizer-instrumented stack switching, and thread-context.
- PHP-loaded ucontext: pinned `config.m4` always selects assembly context on
  the available aarch64 macOS/Linux targets, and its only context flag,
  `--enable-thread-context`, selects thread-context instead. No unmodified PHP
  build can select ucontext on these hosts; it would need a real fallback
  platform or an upstream configure-selector change.
