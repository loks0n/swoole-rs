# TableV2 column ownership

TableV2 is an opt-in typed facade over the Table row/storage core. Original
`swoole::Table`, its layout and direct `column_list` mutations are unchanged.
Declarations are in `swoole_rs_memory_table_v2.h`.

## Storage

TableV2 gets its core from private `Table::make_impl` in collection-free mode;
public `Table::make` uses legacy collection mode. Table has deleted
constructors/destructor; TableV2 uses private friend access to the item-size and
created fields, with no inheritance or reinterpretation.

An opaque `swr_v1_memory_records*` owns an ordered Rust `Vec<Record>`. Each record
owns its name bytes and index/width/kind; a Rust name-to-ordinal index gives
first-name lookup. Duplicate declarations keep all entries and advance item size.
There are no native TableColumn objects, name strings or descriptor mirrors on
this path; the core's map/vector fields are NULL.

`records_declare` validates type, checked width/total and pre-create state, and
reserves record/name/key/index storage before publishing a declaration or
changing item_size. Returns 0 success, -1 allocation/configuration failure, -2
unknown kind (native warning). Failed reserves may keep capacity. Post-create
declarations are refused. Schema mutation/create/close require exclusive
serialization.

## Descriptors

- 40-byte record view: ordinal, generation, index, name_length, width, kind; no
  pointer into Rust memory.
- 32-byte cursor: count, unique_count, position, generation.
- get/next return 1 record, 0 missing/end, -1 error; cursor generation/count must
  match the owner.
- copy validates the view and writes exactly name_length bytes (no NUL) into
  caller storage of sufficient capacity; 0/-1, no writes on failure.

`TableV2::Column` is a transient value: valid()/failed(), kind()/width()/index()/
name_length(), copy_name(char*,capacity) (false marks failed()). columns().next
(Column&) returns bool; failed() distinguishes errors from end. Columns require a
live, unchanged owner; destruction or concurrent schema change is unsupported.

PHP callers copy each name into native scratch and keep it live through Zend
lookup/conversion; no Rust borrow or cursor pointer crosses those effects.

Row wrappers take locked TableRow pointers and return bool: clear_value(row),
get_value(row,long*/double*), get_value(row,char**,TableStringLength*),
set_value(row,value,length). They pass copied scalars to the Rust row operations.
Overlong-string warnings are logged natively with TableRow::set_value attribution.
Callers report failure only after native cleanup/unlock. PHP count must not open a
cursor.

## Clear and close

`records_clear` walks Rust metadata in declaration order using the row-clear
operation; strings clear only the length.

`records_close` nulls the owner field and drops records, names and index without
callbacks or allocation; NULL is idempotent. TableV2 then runs private core
cleanup (row/iterator/pool/mutex/arena) and deletes its facade. That teardown
entry rejects legacy collection custody. All readers must finish before close.
Lookups/cursors may share the sealed owner; row writes/clear need native row locks
or disjoint rows.

Upstream destruction deletes only unique map entries, leaking later duplicate
columns. The record owner frees all records, in declaration order.

## Checks

`tests/modules/memory/table_v2_compat.py` compiles original and selected
`table.cc` plus the typed facade with NDEBUG/-Wall/-Wextra/-Werror under C++14/17/20.
The pinned header always selects `SW_TABLE_USE_PHP_HASH`. A fork witness reads
inherited copy-on-write metadata in a child after schema creation and thread joins,
then updates a shared row under its lock; schema mutation across processes is not
supported. Name-consumer benchmark workloads (65 columns, short names and 80-byte
names with an embedded NUL) exist but are unmeasured.
