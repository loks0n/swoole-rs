# Public status-code array

The native initializer for `swoole::http_server::list_of_status_code` has been
removed. A Rust `static mut [i32; 128]` now defines that C++ data symbol, keeping
every initialized entry, the sentinel and the trailing zero slots. The header's
`extern int[128]` declaration is unchanged.

- Symbol: `_ZN6swoole11http_server19list_of_status_codeE` (Itanium ABI; Mach-O adds
  its prefix), set with `export_name` and kept with `used`.
- Native compilation rejects other C++ ABI families and any int32 size/alignment
  mismatch. Only the tested macOS and Linux targets are known to work.
- Rust never creates a reference to the array. External C++ users keep the original
  unsynchronized sequential read/write contract. There is no accessor or mirror, and
  status lookup does not depend on the array's contents.

Tests: `tests/modules/http/cookie_flow_gate.py --codes-only` (compares all 128 slots
and checks that a shared library linking only the status body defines the symbol
exactly once; the library is not loaded). Export visibility in the production PHP
extension still needs to be checked.
