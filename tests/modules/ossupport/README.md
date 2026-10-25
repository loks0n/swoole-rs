# OS support validation

Each script writes a fresh report under `target/` and exits non-zero on failure.

## Registered gates

- `python3 tests/modules/ossupport/gate.py [--archive FFI_ARCHIVE] [--rust-asan]`
  (`ossupport-policy`): without `--archive` it builds `crates/ossupport` with
  rustc, runs the Rust unit tests and links the static archive; with `--archive`
  it links the supplied archive instead. Either way it runs the C++14
  differential oracle (`differential.cpp`) and the queue caller (`queue.cpp`)
  under ASan/UBSan. `--rust-asan` additionally requires Rust load/store ASan
  imports in the archive.
- `python3 tests/modules/ossupport/php.py --manifest MANIFEST --engine name=swoole.so ...`
  (`ossupport-php`): runs `php_caller.php` (binary read/write/append, 48
  concurrent callers over three reactor/pool teardown-reinit rounds, process pool
  reinit after fork) on each engine and requires identical output. The Rust
  engine must advertise feature bit 131072 and match the manifest's
  `extension_sha256`.

## Other gates

- `activation.py --source CONFIGURED_SOURCE`: compiles every patched unit with
  `SWOOLE_RS_OSSUPPORT` defined via `config.h`, and requires each overlay to
  fail to compile with the flag removed.
- `file_callers.py --source S --patched-file F --library L --rust-archive A [--rust-asan]`:
  File caller (`file_caller.cpp`) linked against original and patched
  `src/os/file.cc`: embedded NUL, full-chunk reads, pread/pwrite offsets, close
  ownership.
- `native_originals.py --source S --patched-source F --library L --rust-archive A --group async|file|msg_queue`:
  runs the unchanged upstream GTests for that group against reference and Rust
  builds. `--linked-only --reference-library` links whole libraries without
  source interposition. `msg_queue` needs `--ipc-namespace` because the original
  uses a fixed SysV key.
- `async_lifetime.py --source S --engine name=libswoole ...`: async worker
  consumers (`async_lifetime.cpp`) against whole native libraries.
- `queue_failure.py --source S --library L`: native queue facade with the
  test-only Rust allocator failure switch.
- `retirement_shutdown.py --reference-source ... --reference-library ... --rust-source ... --rust-library ... --rust-archive ...`:
  deterministic reproducer for pending-retirement notifications at shutdown.
- `sendfile.py --source S --patched-source F --library L --rust-archive A`:
  original/patched `sendfile.cc` with a deterministic syscall stub.
- Body-extraction models, all `--source PINNED_GIT_CHECKOUT`: each extracts the
  pinned and patched native bodies, runs the matching filtered Cargo tests,
  links the module archive into a C++ driver that compares both bodies over a
  scripted syscall space, syntax-checks the whole patched file, and asserts the
  patched function actually calls the Rust helper:
  - `file_progress.py`: `File::read_all/write_all`, 7,680 sequences plus small
    private-file pwrite/append/pread/EOF/EBADF checks.
  - `sendfile_fallback.py`: `!HAVE_SENDFILE` body, 2,520 sequences. On macOS the
    whole file is also syntax-checked with `HAVE_SENDFILE` undefined.
  - `random_bytes.py`: `swoole_random_bytes` outer loop, 1,715 sequences.
  - `file_line.py`: `File::read_line`.
  - `read_content.py`: `File::read_content` with `String::grow`.

`archive_identity.py` is a shared helper (sanitizer stderr classification and
the `--rust-asan` import check).

## Known failures

- `retirement_shutdown.py` reproduces an unconsumed idle-retirement
  notification (`FAILED: idle-retirement notification`); the gate fails until
  that is fixed.
- `native_originals.py --group file` on macOS: Pipe write-end `pread` returns
  `EBADF` where upstream `file.error` expects `ESPIPE`; both engines fail. The
  file group also uses fixed `/tmp` names, so do not run it concurrently on a
  shared host. A minimal test executable can be smaller than the >1MiB
  `bin/core-tests` the upstream fixture assumes.
- Held-lock dispatch allocation failure in the queue is not tested.
- macOS Rust-instruction ASan coverage has not been validated.
