# FixedPool native construction

Both native FixedPool constructors placement-construct the trivial native
`FixedPoolImpl` header before Rust initializes it (compile-time checks require
trivial construction/destruction and standard layout). The borrowed constructor
still rejects NULL, misalignment and address wrap first. The private `impl`
pointer is published only after Rust initialization succeeds.

Header padding: Rust whole-value writes of `repr(C)` structs do not initialize
padding (seven bytes after a slice lock, two trailing pool bytes on the 64-bit
layout). The Rust constructor therefore clears the header bytes and then writes
individual fields; queue allocate/release also write fields individually. Payload
bytes and immutable configuration are never rewritten by queue operations.

Check the selected C++ constructor/queue bodies against a Cargo archive:

```
python3 tests/modules/memory/fixed_native_construction.py \
  --archive HYBRID_BUILD/rust-prefix/lib/libswoole_rs_ffi.a --output UNIQUE_JSON
```

It compiles the hybrid build's bodies under C++14/17 against its header with model allocation effects
(no libc interposition) and checks 24 owned and 60 borrowed cases: counts, physical
size, queue order, payload writes, padding, release choice and canaries. Native
ASan/UBSan does not instrument the linked Rust archive. Native allocator failure,
IPC/fork/thread and Linux runtime behavior are not covered.
