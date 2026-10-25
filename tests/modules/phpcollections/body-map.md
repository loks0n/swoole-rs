# Collection facade source body map

43 original functions (29 Table, 14 Channel), three added native effect bridges
(`table_read_field_value`, `table_set_field_value`, `table_update`) and unchanged
method/alias registration tables, at pin `c7e514509451beafd4d70ce5b78943d51e76381c`.
No original facade function is wholly replaced by Rust. Export reachability is
lexical (direct calls and local helpers); M12 storage dispatch is not counted.
Regenerate the data with `body_map.py --source PINNED --output FILE`; it fails if
the function set or registration table changes without updating its boundaries.

## ext-src/swoole_table.cc

| Function | Original lines | Selected lines | Rust exports (direct/local helper) | Native remainder |
| --- | --- | --- | --- | --- |
| `table_row2array` | 27–48 | 75–84 | `value_plan` | Rust-owned ordered-column cursor selects transient descriptors; native locked dispatch/getters, array materialization and failure propagation remain |
| `table_get_field_value` | 50–72 | 86–89 | `value_plan` | Native lookup and row/Zend materialization dispatcher; Rust chooses complete read/type/error sequence |
| `table_fetch_object` | 82–84 | 99–101 | None | Native Zend layout and authoritative Table pointer |
| `table_get_ptr` | 86–88 | 103–105 | None | Native Zend layout and authoritative Table pointer |
| `table_get_and_check_ptr` | 90–96 | 107–113 | None | Native constructor/ready checks and fatal-error boundary |
| `table_get_and_check_ptr2` | 98–104 | 115–121 | None | Native constructor/ready checks and fatal-error boundary |
| `table_set_ptr` | 106–108 | 123–125 | None | Native Zend layout and authoritative Table pointer |
| `table_free_object` | 110–112 | 127–129 | None | Native Zend allocation/standard object lifecycle |
| `table_create_object` | 114–120 | 131–137 | None | Native Zend allocation/standard object lifecycle |
| `php_swoole_table_minit` | 175–190 | 192–207 | None | Native class/method/alias/property/constant/Iterator registration |
| `swoole_table::__construct` | 192–217 | 209–234 | None | Native constructor-once check, parameter parse, Table allocation/hash callback and pointer publication |
| `swoole_table::column` | 219–241 | 236–258 | `string_invalid` | Native parse/alignment/ready/warning effects; actual Rust record/name/index storage is M12 |
| `swoole_table::create` | 243–255 | 260–272 | None | Native shared-memory creation and size/memory property publication |
| `swoole_table::destroy` | 257–263 | 274–280 | None | Native authoritative storage destruction and pointer clearing |
| `swoole_table::set` | 265–344 | 307–377 | `key_warning`, `value_plan` | Rust ordered-column cursor supplies new-row descriptors; native parse/ready/key warning, row lock/allocation, input iteration, fresh Zend conversion/store/cleanup/unlock/error dispatch remain |
| `swoole_table::incr` | 346–404 | 450–452 | `float_update`, `integer_update`, `kind` | Native parse, lock/row allocation/initialization, Zend conversion, warning/publication/cleanup/unlock; undefined arithmetic domain remains native |
| `swoole_table::decr` | 406–464 | 454–456 | `float_update`, `integer_update`, `kind` | Native parse, lock/row allocation/initialization, Zend conversion, warning/publication/cleanup/unlock; undefined arithmetic domain remains native |
| `swoole_table::get` | 466–488 | 458–487 | `get_action`, `value_plan` | Native parse, row lookup/lock, field/full-row materialization and unlock |
| `swoole_table::exists` | 490–499 | 489–498 | None | Native parse and authoritative row storage operation |
| `swoole_table::del` | 501–511 | 500–510 | None | Native parse and authoritative row storage operation |
| `swoole_table::count` | 513–531 | 512–535 | `count` | Rust ordered-column cursor supplies recursive declaration count; native pointer/parse/normal-mode guard, failure and Zend return remain |
| `swoole_table::getMemorySize` | 533–540 | 537–544 | None | Native storage observations and Zend return/array construction |
| `swoole_table::getSize` | 542–549 | 546–553 | None | Native storage observations and Zend return/array construction |
| `swoole_table::stats` | 551–565 | 555–569 | None | Native storage observations and Zend return/array construction |
| `swoole_table::rewind` | 567–571 | 571–575 | None | Native iterator/row identity and advancement; Zend materialization/return |
| `swoole_table::valid` | 573–577 | 577–581 | None | Native iterator/row identity and advancement; Zend materialization/return |
| `swoole_table::current` | 579–586 | 583–594 | `value_plan` | Native iterator/row identity and advancement; Zend materialization/return |
| `swoole_table::key` | 588–595 | 596–603 | None | Native iterator/row identity and advancement; Zend materialization/return |
| `swoole_table::next` | 597–600 | 605–608 | None | Native iterator/row identity and advancement; Zend materialization/return |

## ext-src/swoole_channel_coro.cc

| Function | Original lines | Selected lines | Rust exports (direct/local helper) | Native remainder |
| --- | --- | --- | --- | --- |
| `channel_coro_fetch_object` | 64–66 | 69–71 | None | Native Zend object layout/pointer and constructor fatal-error boundary |
| `channel_coro_get_ptr` | 68–74 | 73–79 | None | Native Zend object layout/pointer and constructor fatal-error boundary |
| `channel_coro_dtor_object` | 76–89 | 81–94 | None | Native Zend lifecycle, authoritative queue draining, zval/resource destruction and Channel allocation/free |
| `channel_coro_free_object` | 91–95 | 96–100 | None | Native Zend lifecycle, authoritative queue draining, zval/resource destruction and Channel allocation/free |
| `channel_coro_create_object` | 97–103 | 102–108 | None | Native Zend lifecycle, authoritative queue draining, zval/resource destruction and Channel allocation/free |
| `php_swoole_channel_coro_minit` | 105–124 | 110–129 | None | Native class/handler/shortname/property/constant registration |
| `swoole_channel_coro::__construct` | 126–141 | 131–144 | `capacity` | Native parse, authoritative Channel allocation and capacity publication |
| `swoole_channel_coro::push` | 143–167 | 146–184 | `channel_plan` | Native parse, zval custody, queue operation/suspension, fresh result/error observation, property/return publication and reference/container cleanup |
| `swoole_channel_coro::pop` | 169–189 | 186–220 | `channel_plan` | Native parse, zval custody, queue operation/suspension, fresh result/error observation, property/return publication and reference/container cleanup |
| `swoole_channel_coro::close` | 191–194 | 222–225 | None | Native authoritative queue operation/observation and Zend return/array construction |
| `swoole_channel_coro::length` | 196–199 | 227–230 | None | Native authoritative queue operation/observation and Zend return/array construction |
| `swoole_channel_coro::isEmpty` | 201–204 | 232–235 | None | Native authoritative queue operation/observation and Zend return/array construction |
| `swoole_channel_coro::isFull` | 206–209 | 237–240 | None | Native authoritative queue operation/observation and Zend return/array construction |
| `swoole_channel_coro::stats` | 211–217 | 242–248 | None | Native authoritative queue operation/observation and Zend return/array construction |

M12 owns all record/name/index storage and the private core column-container
policy. M27 uses transient descriptors, typed row operations and native name
scratch, with explicit cleanup on failed lookup/name/store/cursor. No native
Column objects or metadata mirrors remain in the selected path; the public
`Table` class is unchanged.
