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

- `sendfile.py --source S --patched-source F --library L --rust-archive A`:
  original/patched `sendfile.cc` with a deterministic syscall stub.
- Body-extraction models, all `--source PINNED_GIT_CHECKOUT`: each extracts the
  pinned and patched native bodies, runs the matching filtered Cargo tests,
  links the module archive into a C++ driver that compares both bodies over a
  scripted syscall space, syntax-checks the whole patched file, and asserts the
  patched function actually calls the Rust helper:
  - `read_content.py`: `File::read_content` with `String::grow`.

`archive_identity.py` is a shared helper (sanitizer stderr classification and
the `--rust-asan` import check).

## Known failures

- Held-lock dispatch allocation failure in the queue is not tested.
- macOS Rust-instruction ASan coverage has not been validated.
