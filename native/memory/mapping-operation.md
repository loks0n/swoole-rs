# SharedMemory operation control

`shared_memory.cc` drives allocation, release, protection and relocation through
one callback-free Rust cursor, `swr_v2_memory_mapping_step` (memory feature bit
64). Public functions, private static method signatures, the 8-byte mapping header
and existing C exports are unchanged.

- 64-byte control and 32-byte effect records hold copied scalars and borrowed
  memory tokens. Native resumes the cursor only after executing the requested
  effect.
- Rust owns extent normalization, header initialization, release/protection extent
  decoding, operation order, payload copying and terminal publication. It never
  constructs a File, performs an OS call, logs, sets errno or calls back. Native
  supplies platform flags and results.
- The non-anonymous backend keeps the real `File("/dev/zero", O_RDWR)` and its
  scope; selected source includes the File header it needs. Warnings keep their
  original `alloc`/`free` attribution.
- Relocation requests the new allocation before reading the old header. Rejected
  new storage is freed with global `sw_shm_free`; old storage, after copying, with
  private `SharedMemory::free`. No header is read after unmap.
- The bounded copy (see contract.md, Shared mapping) replaces upstream's realloc
  overread.

Source/model gate (C++14/17; anonymous, non-anonymous and no-MAP_FAILED
configurations; model mmap/munmap/mprotect over local arrays, no libc replacement;
plus a C11 ABI check):

```
python3 tests/modules/memory/mapping_operation.py \
  --source PINNED_TREE --archive ACTUAL_FFI_ARCHIVE --output UNIQUE_JSON
```

The caller must ensure the archive was built from the tested source. Real OS
failure, errno, IPC/fork/thread and Linux runtime behavior are not covered.
