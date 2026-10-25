# Table value operation pipeline

`swr_v1_phpcollections_value_plan` is additive. It receives only copied
operation/type/presence/null metadata and returns at most three action bytes,
low byte first. No allocation, native pointer, name, value, callback or iterator
enters or remains in Rust. Invalid operations return no plan. Native callers use
only the constant operations 1, 2 and 3.

| Operation | Meaning |
| --- | --- |
| 1 | Read one field. Absent returns false; present integer/double/string loads then publishes the scalar. Unknown read kinds keep the native invariant abort. |
| 2 | Load then insert into the array under the native column name. |
| 3 | Write. Absent/null new cells are cleared; otherwise convert then store, releasing the string temporary after store. Existing rows convert explicit null and keep the original integer fallback for unknown write tags. |

Native dispatchers execute the complete plan after Rust returns. Row
getter/setter, Zend conversion/materialization, string release and abort stay
native. Kind is observed before conversion/getter; name is observed at array
insertion after the getter. Nothing is prefetched across effects, and no C++
effect runs inside a Rust frame. Warnings, locks and cleanup order are unchanged.
Missing-field reads do not touch column metadata. Callers use transient column
descriptors and typed row operations; this ABI contains no native `TableColumn`
type or layout.

Existing-row Zend input traversal, numeric/missing-field filtering, row
allocation/error paths and the native iteration/effect loops remain native.
