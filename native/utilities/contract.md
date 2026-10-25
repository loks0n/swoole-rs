# Utilities ABI

Opt-in feature bit 512 (`SWOOLE_RS_UTILITIES`). Patches `src/core/misc.cc`,
`src/core/log.cc`, `include/swoole_util.h`, `include/swoole.h` and
`include/swoole_log.h`. Declarations are in
[swoole_rs_utilities.h](swoole_rs_utilities.h). Tests:
`tests/modules/utilities/README.md`. Depends on the locks module for wait/wake.

## General rules

- Supported hosts are LP64 macOS/Linux.
- No C++ object layout, Rust reference, allocator or PHP callback crosses the v1
  ABI. Borrowed byte ranges are valid for their stated length; outputs are aligned,
  writable and disjoint from inputs. Null input is allowed only at length 0.
  Lengths above `isize::MAX` are rejected. No borrow survives a call.
- Callers pass host `char` signedness explicitly (`signed_char`), so
  `-funsigned-char` builds keep their arithmetic and ctype promotions.
- ctype/libc functions (`tolower`, `isspace`, `strncasecmp`, `memchr`, `memcmp`)
  are the host's, so locale behavior is unchanged. Invalid negative ctype arguments
  are undefined upstream and outside parity.
- Step functions use a caller-local `uint32_t` phase initialized to 0. Rust returns
  an action; native code performs it and calls again with refreshed facts. All IO,
  allocation, warnings and field writes happen natively between steps. Null or
  unknown phase returns INVALID without reading facts.

## Byte helpers

- `swr_v1_utils_lowercase(bytes, int32 length, signed_char)`: in-place
  `swoole_strtolower` traversal with host `tolower` once per byte, including after
  NUL. Nonpositive length does no access.
- `swr_v1_utils_hash(bytes, len, algorithm, signed_char)`: 0 PHP/DJBX33A (64-bit
  wrapping), 1 Jenkins (original u32/u32/u64 mix and truncated block counter),
  2 Austin (64-bit state, signed-int promotions). Unknown algorithm or invalid range
  returns 0. Austin has undefined negative left shifts on high bytes upstream; only
  ASCII Austin input is defined parity, Rust wraps deterministically otherwise.
- `swr_v1_utils_pretty_range`: offset/length for `Logger::get_pretty_name`. Never
  writes input. Invalid outputs/ranges return -1; outputs are zeroed first; no
  bracket returns an empty span. Native builds the `std::string` afterwards.
- `swr_v1_utils_trim(bytes, len, right, signed_char)`: skipped prefix count, or
  retained suffix length. Native mutable rtrim zeros the removed bytes.
- `swr_v1_utils_find(hay, len, needle, len, mode)`: 0 binary (`memchr`), 1 libc
  casefold (`strncasecmp` with exact-first-byte guard), 2 reverse (excludes
  offset 0). Returns offset or -1. Needle must be nonempty; reverse needs
  length >= needle.
- `swr_v1_utils_compare(a, alen, b, blen, mode)`: 0/1 C-string equality plain/casefold,
  2/3 C-string prefix plain/casefold, 4 binary prefix, 5 binary suffix. Length guards
  short-circuit before access; C modes call host `strncmp`/`strncasecmp` and may stop
  at an early NUL. Binary modes keep embedded NULs. Empty compared ranges return true.
- `swr_v1_utils_partition(bytes, len, separator, before)`: bytes before/after the
  first separator (`memchr`), or -1.

### v2 inline publication

All public utility signatures are unchanged; v1 is frozen.

- `swr_v2_utils_ltrim(char **cursor, length, signed_char)`: length 0 does not read
  the cursor slot. Follows the original NUL short circuit and publishes each cursor
  increment; returns remaining length.
- `swr_v2_utils_rtrim(data, length, signed_char)`: walks backwards, clearing each
  whitespace byte before visiting its left neighbor. Length 0 does no access.
- `swr_v2_utils_search(hay, len, needle, needle_len, mode)` returns
  `SwrUtilsSearchResult {pointer, offset, uint32 needle_length}`. Modes: 0 binary,
  1 libc casefold, 2 reverse (discovers the C-needle length with native uint32
  narrowing). The pointer is derived from the input pointer; miss returns null/-1.
  Native debug assertions run after return.

## Concurrency primitives

- `swr_v1_utils_spinlock(u32 *, cpus, backoff_limit)`: SeqCst compare-exchange like
  native `__sync`, relaxed reads, `spin_loop` backoff, OS thread-yield on exhaustion.
  Caller unlocks with its existing native release store. Backoff multiplication is
  checked. Null/unaligned pointers return immediately.
- `swr_v1_utils_wait(u32 *, timeout, have_futex)` / `swr_v1_utils_wakeup(u32 *, n, have_futex)`:
  reuse the locks module's Rust implementation. `have_futex` is the configured
  `HAVE_FUTEX` (0/1); Linux uses the futex path when enabled, otherwise the polling
  fallback. Caller owns aligned process-shared storage and its lifetime. errno is
  preserved. Timeouts outside the positive `time_t` range are undefined upstream.

## Logger

### Formatting

- `swr_v1_utils_log_level(int)` clamps to 0..6. `log_label`/`log_rotation` return
  static NUL-terminated strings. Unknown levels map to INFO; unknown rotations
  (including SINGLE queried directly) map to the daily format.
- `swr_v1_utils_log_line(out, cap, ...)`: exact `Logger::put` line. Signed precision
  matches printf: negative reads through NUL, zero is empty. Each input is readable
  through its first NUL or nonnegative precision; null input only at precision 0.
  Capacity 0 permits null output and returns the full required length. Positive
  capacity writes at most cap-1 plus NUL (`sw_snprintf`). Counts above `INT_MAX`
  return `SIZE_MAX`; native then publishes `EOVERFLOW` and zero bytes. Capacity must
  be <= `INT_MAX`.
- `swr_v1_utils_log_micros(out, cap, int64)`: the `<.%lld>` suffix, same output rules.

### Stateless step controllers (v1)

- `swr_v1_utils_redirect_step`: stdout/stderr redirection (`SwrUtilsRedirectAction`).
  Upstream behavior is kept, not repaired: stderr dup failure leaves the saved stdout
  descriptor owned; restore failures warn and still restore the other stream, close
  both saved values and reset state; close results are ignored.
- `swr_v1_utils_log_file_step`: operations open 0, close 1, reopen 2
  (`SwrUtilsLogFileAction`). Open closes the old stream before copying the new path,
  selects rotation before open, and warns before clearing fields on failure. Opened
  is set before an unchecked `fdopen` (upstream). Close ignores `fclose`; stdout is
  restored only for an opened stream. Reopen saves the path before close, ignores
  open's result, then tests the redirected flag.
- `swr_v1_utils_log_put_step` / `swr_v1_utils_log_emit_step`: emission sequence
  (level filter, date, rotation, micros, identity, format, mutex/FILE lock, write,
  flush, unlock, backtrace). Emit adds rotation try-lock/reopen/unlock and worker PID
  fallback/symbol. Write/flush failures are ignored. Backtrace is tested after the
  mutex is released. The native rotation scope (including temporary string
  destruction) must finish before the micros phase.
- `swr_v1_utils_log_config_step`: reset 0, date 1, stream 2. Reset returns
  `SwrUtilsLogDefaults` (`%F %T`, INFO, single, no microseconds). Date rejection sets
  last_error before the warning; stream replacement closes before publishing.

Field observation rule: callers read only the Logger field that belongs to the
current observation phase and pass 0 for unused facts. `opened` is read only at
`SWR_UTILS_LOG_PUT_FILE_LOCK_PHASE` and `SWR_UTILS_LOG_PUT_FILE_UNLOCK_PHASE`, while
the mutex is held; reading it outside the lock is a data race. For file steps: open
reads opened in phase 0 and rotation in phase 2; close reads opened only; reopen
reads opened in phase 0 and redirected in phase 3. Redirection phase 0 reads opened
only when enabling, then redirected only if opened; disabling reads redirected only.

### Logger state ABI 2

`SWOOLE_RS_LOGGER_STATE_ABI 2` changes the selected Logger's C++ layout: it stores
one opaque `SwrUtilsLogState` handle (`swr_v1_utils_log_state_*`) instead of native
fields. Consumers must rebuild against the selected SDK; native-layout clients are
incompatible. Public method signatures are unchanged.

- `create(native_max, &out)` sets `*out` to null and publishes only a complete
  allocation. `destroy` frees the sole handle once all users are quiescent; it never
  closes FILEs or descriptors.
- Status: 0 OK, 1 length -> `std::length_error`, 2 capacity -> `std::length_error`,
  3 allocation -> `std::bad_alloc`, 4 invalid. C++ throws after return.
- Text setters reserve fallibly before publication and keep a trailing NUL; input may
  alias current text. Returned text pointers are valid until the corresponding
  mutation or destruction.
- Configuration is single-threaded. Native put/reopen keep mutex custody. Reset
  changes only date format, microseconds, rotation and level. Close clears the
  logical filename and opened flag but keeps the resolved filename; failed-open
  cleanup clears both paths after diagnostics.

`swr_v1_utils_log_path_*` owns temporary filenames:

- `create` operation 0 copies the logical C filename before close; operation 1 copies
  a binary filename before calendar effects. Output starts null.
- `rotate` appends `.` and the formatted date after native strftime; on failure the
  old value is intact.
- `get` borrows bytes (with trailing NUL) until destroy/adopt.
- `adopt` consumes the path only on success and moves its buffer into resolved state
  without another allocation.
- `path_emit_step` compares against the resolved C filename only at phase 14.

Reopen keeps its captured filename until function exit; put keeps the scoped owner to
the end of the rotation block. Only public `gen_real_file` constructs a
`std::string`. Rust allocations differ from native `std::string`/SSO, so allocation
and exception points can move.

## Logging macros (v2)

`include/swoole_log.h` macros call two whole-program exports. Contexts are caller
stack PODs, uniquely borrowed for one step. No allocation, registry or Logger layout
change. `fatal_error` is the original forwarder.

`swr_v2_utils_log_frontdoor_step(ctx, operation, first, second, unsigned_width, high)`
returns `SwrLogAction {action, level}`.

- Operations 0..9: info, notice, warning, debug, trace, sys_notice, sys_warning,
  error_log, error, sys_error.
- Actions 0..7: done, publish, threshold, mask, ignored, format, put, exit. Facts
  answer only the preceding action.
- `unsigned_width`: 0 signed, 32/64 usual unsigned comparison, 128/129 for
  unsigned/signed 128-bit (with `high`), 256 a host floating `>=` result, 257 a
  completed user-type condition.

Operand rules: arithmetic and enum operands are marshalled with the usual integer
conversions; floating operands are compared with host C++ `>=` before entering Rust
(no float-to-int conversion). User-defined comparison types and enums with ADL
`operator>=` keep the exact original conditional expression natively; Rust consumes
only its truth value. Class/noncopyable operands are never copied. All argument
expressions, including `__func__`/`__PRETTY_FUNCTION__`/`__SW_FUNC__`, run in the
caller's scope; there are no lambdas or callbacks. For `error_log`, the error is
evaluated at publication, ignored query and formatting separately, and the level at
admission and output separately.

Bare-if macros stay bare `if` statements: the guard runs the pure program up to its
FORMAT or MASK request, the format expression stays in the caller, and a fresh
context resumes at phase 4 for output, so `else` binding is preserved. Other macros
keep `do/while`. Compiled-off debug/trace macros evaluate nothing.

`swr_v2_utils_log_hex_step(ctx, length, count)` owns row iteration, offsets,
per-byte effects, printability and header/footer decisions. Actions: 0 done,
1 header, 2 hex format, 3 ctype, 4 text byte, 5 text dot, 6 row, 7 footer. Native
`sprintf` counts feed unsigned wrapping accumulators. Data and length are captured
once. Each byte is re-read for hex format, for ctype, and (if printable) for text.

Unqualified: late non-ADL or block-scope enum operator lookup, unparenthesized macro
arguments that change precedence (bare assignment/ternary), numeric argument
evaluation order (compiler-specific), GNU statement expressions, and actual exit
behavior. On Linux, an ASan-instrumented utility archive cannot be loaded into PHP
because PHP uses `RTLD_DEEPBIND`; PHP-level tests use a plain archive.
