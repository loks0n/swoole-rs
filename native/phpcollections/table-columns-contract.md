# PHP Table column record callers

Rust (memory module, TableV2) owns the ordered column records, the first-name
index and the name bytes. phpcollections callers receive transient by-value
column descriptors; there is no native `TableColumn` allocation, persistent
metadata/name mirror, C++ vector reference or Rust span. The original public
Table factory and layout are unchanged.

- All private Table pointer sites and the factory use TableV2.
- Declaration cursors return one copied descriptor at a time. A missing lookup
  and a failed lookup are distinct results.
- Native-owned scratch copies a name before Zend hash lookup, or (after the row
  getter) before array insertion. One scratch string is reused per traversal.
  Scalar reads need no name copy.
- No Rust borrow or frame spans Zend conversion/materialization, row access,
  locking or cleanup.

Failure ordering:

- Read failures run `get`'s unlock and partial-output cleanup (or `current`'s
  partial-output cleanup) before the error is published.
- Write failures still release a planned string before returning false; `set`
  then unlocks before the error.
- Name/lookup/cursor failures use the same boundary.
- Numeric arithmetic keeps the original pre-conversion scalar snapshot point
  (using the copied index), then stores through the typed descriptor. Overflow
  policy is unchanged.

`count` without recursion does not open a cursor; recursive count includes
duplicates. Full materialization and initialization preserve order and duplicate
semantics. Rust owns and reclaims every record and name; there is no native column
cleanup loop. Row access, locks, Zend lifecycle, effect dispatch and existing-row
numeric/missing-key filtering remain native. No original PHP function is wholly Rust.
