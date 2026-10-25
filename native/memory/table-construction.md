# Table storage construction

Legacy Table and TableV2 both call `Table::create`. Rust chooses the whole
arena -> conflict pool -> iterator -> publication sequence, reusing the existing
logical/physical layout and creation/publication ABI. It computes the pool's
interior address and initializes the row-pointer array and row headers before
the native pool constructor runs. Native code only dispatches effects, logs,
marshals tokens and transfers RAII custody.

- 120-byte cursor: the 112-byte creation snapshot plus a phase. 32-byte result:
  native memory token, two byte sizes, action.
- Native allocates the shared arena and constructs FixedPool and TableIterator
  after Rust returns, recording each token before resuming.
- Rust publishes metadata/created once all three resources exist and the schema is
  unchanged. Native RAII keeps rollback custody until then; native exceptions
  propagate outside Rust.
- Single-use, externally serialized. No frame, borrow, callback, class object or
  lock crosses a Rust call.

Public C creation API/layout, Table class, TableV2 descriptor API, row layout and
lock operations are unchanged.

## Initial object factory

`Table::make_impl` uses a 48-byte Rust factory transaction. It normalizes
rows/conflict before native Table allocation, then selects native Mutex and, in
legacy mode only, the public column vector. Final resume initializes scalar fields
and creates the Rust legacy name index. Collection-free mode (TableV2) creates
neither vector nor name index. Native publishes tokens/hash function and releases
RAII after return 0. Native constructor-exception cleanup behavior is unchanged
and untested.

## Commands

```
cargo test --locked -p swoole-rs-memory construction_sequences_normal_storage_effects_before_single_publication
cargo test --locked -p swoole-rs-memory factory_sequences_actual_modes_and_initializes_only_after_native_tokens
cargo build --locked --release -p swoole-rs-memory
cc -std=c11 -Wall -Wextra -Werror -Inative/memory tests/modules/memory/table_construction.c \
  target/release/libswoole_rs_memory.a -lpthread -ldl -lm -o OUT/construction
OUT/construction
python3 tests/modules/memory/table_v2_compat.py --source /pinned/reference --output OUT/syntax.json
```

On macOS omit `-lpthread -ldl -lm`. The C fixture links the Cargo archive and runs
54 factory cases and 27 storage-construction cases (64/128/256 rows, 8/16/24-byte
payloads, conflict 0.2/0.5/1.0) with model pool/iterator tokens; the real
constructors are not executed. `table_v2_compat.py` is a C++14/17/20 syntax check.
