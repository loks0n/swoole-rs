# PHP Event frontend

M28 moves Event policy to Rust: the immutable method/legacy-alias catalogue,
descriptor routing, `Event.add` admission and publication, extended stream
conversion, passive `isset`, write/delete/cycle policy, callback-result
dispatch, reactor initialization/admission and the `loop`
wait/exit/dispatch/rshutdown control. Native callers perform every Zend,
callback, allocation, descriptor and reactor effect after Rust returns. Rust owns
the private registry metadata (an opaque handle in the native adapter); native
keeps sockets, payloads and callbacks. The native fallback keeps the original
`unordered_map` and byte-original bodies inside the feature guard. See
[`native/phpevents/contract.md`](../../../native/phpevents/contract.md) for the
ABI and open work.

Edit the overlay in `migration/patches/phpevents/` with `tools/patches.py`; see
[hybrid build](../../../docs/hybrid-build.md#editing-patches).

## Ordinary modeled comparison (`gate.py`)

```sh
python3 tests/modules/phpevents/gate.py --source PINNED_SOURCE \
  --sanitize --output target/phpevents-ordinary.json
```

Runs the full original and selected bodies against modeled native APIs, for
both socket-capability profiles: 11 alias registrations, 20/23 descriptor
scenarios, 7 successful registrations, 12 extended-stream conversions with exact
ordered native effects, 160 passive `isset` combinations, update/write/delete/
cycle cases and six callback-result dispatcher cases. It also checks the public
method table stays byte-exact, compiles `callback_pair_abi.c` as C11 and links it
against the Rust archive. `--rust-sanitize` (with `--sanitize`) instruments the
Rust module with ASan and checks its object imports; prebuilt Rust std is
uninstrumented. Registered in `tools/dev.py` as `phpevents-policy`.

Not executed: real descriptors, event loop, callback invocation or replacement,
backend failure, allocator failure/OOM, shutdown, retirement, fault injection or
IPC. Error branches are unexecuted.

## Full translation-unit compile (`sdk.py`)

```sh
python3 tests/modules/phpevents/sdk.py --source PINNED_SOURCE \
  --sdk-export SELECTED/export.json --native-export NATIVE --output UNIQUE.json
python3 tests/modules/phpevents/sdk.py --source PINNED_SOURCE \
  --sdk-report COMPLETED_PHPHELPERS_SDK --output FILE
```

Copies immutable producer SDKs (or a completed phphelpers SDK capture), verifies
their recorded hashes, and compiles the complete Event TU for native/Event-only/
combined, sockets off/on and C++14/17 with `-Werror`. It requires every current
Rust import in selected objects and none in native objects, and fails if a
selected-only header is relabeled as native by disabling its feature macros.
`--native-export DIR` selects the observed production flags/config and checks
exact `CXXFLAGS`. Registered as `phpevents-sdk`.

## Unit tests

```sh
cd tests/modules/phpevents && python3 -m unittest test_identity.py
```

`test_identity.py` covers `sdk.py`'s object-import checks.

## Originals

The PHPT gate (merge tier `phpt-*` jobs) runs all 20 pinned `swoole_event`
originals on upstream and on the all-modules hybrid.

## Gate audit (#492)

Kept (2):

- `phpevents-policy`: the full original and selected bodies against modeled
  native APIs, with exact ordered effects. It also checks the byte-exact method
  table and links the C11 ABI caller against the Rust archive.
- `phpevents-sdk`: the only complete compile of the Event file, for native,
  Event-only and combined builds, with sockets off and on, at C++14/17 with
  `-Werror`. It also checks that selected objects import Rust and native
  objects don't.

Deleted (1): `phpevents-descriptors` loaded both engines to compare the method
catalogue, four scalars, one plain-file conversion and one idle `isset`. The
20 `swoole_event` PHPTs exercise the same calls on real descriptors in both
engines, and `api-surface` compares the reflected catalogue, including aliases.
Its Rust-caller check repeats `phpevents-sdk`'s import check.
