# Collection facade native remainder

`Swoole\Coroutine\Channel` is wholly Rust (crates/phpcollections, over the
coroutine module's C++ queue); this file covers `Swoole\Table`.

| Area | Rust ownership/decisions | Native remainder |
| --- | --- | --- |
| Table columns | M12 TableV2 sole nonempty ordered store, index, growth, custody and cursor state; M27 invalid string-size decision | Constructor/pointer/ready checks, alignment/type narrowing, warnings; legacy public Table ABI (private V2 core uses no column containers) |
| Table set | Ordered new-row tokens, key warning and new/null/update conversion/store/release plans | Row lock/allocation, input iteration, fresh Zend conversion/store/string release, error cleanup/unlock |
| Table incr/decr | Kind and representable integer/double arithmetic | Shared native update dispatcher, row initialization, conversion/defaults, warnings/publication/unlock; undefined overflow/casts remain outside qualified domains |
| Table read/count | Ordered tokens/count, missing/field/full-row choice, whole materialization/type/error plans and count arithmetic | Row lookup/locks/getters, native dispatch, Zend materialization and explicit cursor-error propagation |
| Table other methods | No whole-method replacement | Native iterator identity/advance, exists/delete, size/memory/stats and object/class/property lifecycle |

All 27 private Table pointer sites/factory use TableV2. No selected PHP Table
`column_list` access remains. Returned native Column facts are freshly read after
Rust returns; Zend conversion/cleanup, locks and callbacks never run through Rust
frames. Cursor failures stay distinct from end/empty. Normal count avoids opening
a cursor; set/get unlock before Zend error effects. No mirror column store exists.
Legacy public C++ Table/vector ABI and direct callers remain unconverted.

Allocation/lifetime differs: pinned Table::destroy deletes only unique tokens
from column_map; later duplicate declarations retained only in column_list leak.
Current TableV2 owns record/name bytes in Rust and has no Native Column objects.
Its private core allocates no legacy column map/vector. Public
Table::make/layout/destroy keep original behavior. Allocation topology and original
duplicate leak/deletion traces therefore differ.

Linux `force_unlock` misses its expected native warning in the complete
original profile. The mixed `serialize_deny` original is not run here;
cancellation originals belong to M06/shared gates.

Open gates: fresh loaded production and originals for the current TableV2
source, Zend bailout/GC/destructor reentry, allocator failure, cancellation and
races, loaded ZTS, other platforms/widths, FP modes/NaN payloads and optimized
performance. LLP64 is refused. Existing-row numeric/missing-key filters, row
allocation and native effect loops remain native.
