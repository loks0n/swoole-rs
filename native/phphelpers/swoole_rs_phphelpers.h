#ifndef SWOOLE_RS_PHPHELPERS_H
#define SWOOLE_RS_PHPHELPERS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Native Zend storage/effects remain authoritative. Borrowed initialized spans
 * are used only during each call. No callback or allocation occurs in Rust. */
/* Common Native async admission: initialized phase0; blocking skips context.
 * Native observes context only on request, then invokes fn/async after return.
 * No callback/context representation or frame crosses these Native effects. */
enum SwrPhpAsyncAction { SWR_PHP_ASYNC_DONE=0, SWR_PHP_ASYNC_OBSERVE_COROUTINE=1,
    SWR_PHP_ASYNC_DIRECT=2, SWR_PHP_ASYNC_DISPATCH=3 };
uint32_t swr_v1_phphelpers_async(uint32_t *phase, uint8_t blocking, uint8_t coroutine);
/* Native parsing/string-length/array-count observation occurs before this call. */
uint8_t swr_v1_phphelpers_empty(size_t count);
/* Public native String/CharPtr lifecycle; initialized phase0, copied observations.
 * op0 release;1 copy assignment;2 move assignment;3 release/copy;4 retain/take.
 * Observe means native presence for0, self identity for1; no other reads.
 * Native executes every action only after Rust returns, then refreshes facts. */
enum SwrPhpStringAction { SWR_PHP_STRING_DONE=0, SWR_PHP_STRING_OBSERVE=1,
    SWR_PHP_STRING_RELEASE=2, SWR_PHP_STRING_RESET=3, SWR_PHP_STRING_COPY=4,
    SWR_PHP_STRING_MOVE=5, SWR_PHP_STRING_RESET_SOURCE=6, SWR_PHP_STRING_ALIAS=7 };
uint32_t swr_v1_phphelpers_string_plan(uint32_t *phase, uint32_t operation, uint8_t observation);
/* Native KeyValue ctor0/insert1/dtor2; Variable retained-copy3/move4.
 * Phase0; key presence observed freshly on request. Native storage/effects only. */
enum SwrPhpValueAction { SWR_PHP_FACADE_DONE=0, SWR_PHP_FACADE_OBSERVE_KEY=1,
    SWR_PHP_FACADE_RETAIN_KEY=2, SWR_PHP_FACADE_NULL_KEY=3,
    SWR_PHP_FACADE_DEREFERENCE=4, SWR_PHP_FACADE_COPY=5, SWR_PHP_FACADE_RETAIN=6,
    SWR_PHP_FACADE_INSERT_STRING=7, SWR_PHP_FACADE_INSERT_INDEX=8,
    SWR_PHP_FACADE_RETAIN_INSERTED=9, SWR_PHP_FACADE_RELEASE_KEY=10,
    SWR_PHP_FACADE_DESTROY=11, SWR_PHP_FACADE_RESET_SOURCE=12 };
uint32_t swr_v1_phphelpers_value_plan(uint32_t *phase, uint32_t operation, uint8_t key_present);
/* Inline Callable duplicate: native allocation precedes phase0. */
enum SwrPhpDuplicateAction { SWR_PHP_DUPLICATE_DONE=0, SWR_PHP_DUPLICATE_CACHE=1,
    SWR_PHP_DUPLICATE_VALUE=2, SWR_PHP_DUPLICATE_RETAIN=3,
    SWR_PHP_DUPLICATE_OBSERVE_NAME=4, SWR_PHP_DUPLICATE_NAME=5 };
uint32_t swr_v1_phphelpers_duplicate_plan(uint32_t *phase, uint8_t name_present);
/* Native callable factory0 / nullable factory1, phase0; observations lazy. */
enum SwrPhpFactoryAction { SWR_PHP_FACTORY_NULL=0, SWR_PHP_FACTORY_OBSERVE_READY=1,
    SWR_PHP_FACTORY_DELETE=2, SWR_PHP_FACTORY_RETURN=3,
    SWR_PHP_FACTORY_OBSERVE_POINTER=4, SWR_PHP_FACTORY_OBSERVE_NULL=5,
    SWR_PHP_FACTORY_CREATE=6, SWR_PHP_FACTORY_OBSERVE_CREATED=7,
    SWR_PHP_FACTORY_NULL_ERROR=8, SWR_PHP_FACTORY_INVALID_ERROR=9 };
uint32_t swr_v1_phphelpers_factory_plan(uint32_t *phase, uint32_t operation,
                                      uint8_t observation, uint8_t allow_null);
/* Whole sparse/indirect iterator policy; native bounds/storage/API decoding. */
enum SwrPhpIteratorAction { SWR_PHP_ITERATOR_DONE=0, SWR_PHP_ITERATOR_OBSERVE_END=1,
    SWR_PHP_ITERATOR_READ_VALUE=2, SWR_PHP_ITERATOR_OBSERVE_POINTER=3,
    SWR_PHP_ITERATOR_OBSERVE_INDIRECT=4, SWR_PHP_ITERATOR_DEREFERENCE=5,
    SWR_PHP_ITERATOR_OBSERVE_UNDEFINED=6, SWR_PHP_ITERATOR_ADVANCE=7,
    SWR_PHP_ITERATOR_OBSERVE_KEY=8, SWR_PHP_ITERATOR_PUBLISH_STRING=9,
    SWR_PHP_ITERATOR_PUBLISH_INDEX=10 };
uint32_t swr_v1_phphelpers_iterator_plan(uint32_t *phase, uint8_t observation);
enum SwrPhpKind { SWR_PHP_UNDEF=0, SWR_PHP_NULL=1, SWR_PHP_BOOL=2,
    SWR_PHP_LONG=3, SWR_PHP_DOUBLE=4, SWR_PHP_STRING=5,
    SWR_PHP_ARRAY=6, SWR_PHP_OBJECT=7, SWR_PHP_RESOURCE=8, SWR_PHP_OTHER=9 };
/* Complete PCRE wrapper lifecycle. Native parsing/cache/refcounts/library call
 * and Zend return values remain native. Phase0, fresh compiled result. */
enum SwrPhpRegexAction { SWR_PHP_REGEX_DONE=0, SWR_PHP_REGEX_COMPILE=1,
    SWR_PHP_REGEX_INITIALIZE=2, SWR_PHP_REGEX_INCREF=3, SWR_PHP_REGEX_MATCH=4,
    SWR_PHP_REGEX_DECREF=5, SWR_PHP_REGEX_FALSE=6 };
uint32_t swr_v1_phphelpers_regex(uint32_t *phase, uint8_t compiled);
/* Eleven immutable standard-library wrapper target/argument-position bindings.
 * Native per-wrapper function cache remains authoritative. Output on success. */
typedef struct { const char *name; size_t length; int32_t position; } SwrPhpWrapper;
uint8_t swr_v1_phphelpers_wrapper(uint32_t index, SwrPhpWrapper *output);
/* Ordered complete stdext registration. Native handler/cache storage remains
 * authoritative. Cursor0, disjoint writable step; names are static immutable. */
typedef struct { uint32_t index; const char *name; size_t length; } SwrPhpInitStep;
enum SwrPhpInitAction { SWR_PHP_INIT_DONE=0, SWR_PHP_INIT_OPCODE=1,
    SWR_PHP_INIT_LOOKUP=2, SWR_PHP_INIT_REPLACE=3 };
uint32_t swr_v1_phphelpers_init_next(size_t *cursor, SwrPhpInitStep *step);
/* Read-only known bytes retain frozen SW_ZEND_KNOWN_STRINGS enum order.
 * Native global persistent/interned pointer storage remains authoritative.
 * Cursor/length are independent initialized native size_t storage. */
size_t swr_v1_phphelpers_known_count(void);
const char *swr_v1_phphelpers_known_next(size_t *cursor, size_t *length);
enum SwrPhpReleaseAction { SWR_PHP_RELEASE_DONE=0, SWR_PHP_RELEASE_OBSERVE_VALUE=1,
    SWR_PHP_RELEASE_VALUE=2, SWR_PHP_RELEASE_OBSERVE_NAME=3, SWR_PHP_RELEASE_NAME=4 };
/* Phase0, freshly observed value-defined then name-present AFTER native dtor. */
uint32_t swr_v1_phphelpers_release(uint32_t *, uint8_t observation);
/* family array=0/string=1/stream=2. Static immutable NUL-terminated result;
 * output length excludes terminator. Unknown name returns null and length0. */
const char *swr_v1_phphelpers_alias(uint32_t, const uint8_t *, size_t, size_t *);
typedef struct SwrPhpArgumentPlan { uint32_t head, tail_begin, tail_count; } SwrPhpArgumentPlan;
/* Defined source domain: count>position>=0; source/destination zvals disjoint.
 * Native copies [1..=head] to destination0, source0 to head, then tail. */
uint8_t swr_v1_phphelpers_arguments(int32_t, int32_t, SwrPhpArgumentPlan *);
enum SwrPhpMergeAction { SWR_PHP_MERGE_DONE=0, SWR_PHP_MERGE_ADD=1,
    SWR_PHP_MERGE_FIND=2, SWR_PHP_MERGE_APPEND=3, SWR_PHP_MERGE_PROMOTE=4 };
/* Phase0; inserted observed only after ADD, existing_array only after FIND. */
uint32_t swr_v1_phphelpers_merge(uint32_t *, uint8_t inserted, uint8_t existing_array);
enum SwrPhpKeyedMergeAction { SWR_PHP_KEYED_DONE=0,
    SWR_PHP_KEYED_ADD_INDEX=1, SWR_PHP_KEYED_ADD_STRING=2,
    SWR_PHP_KEYED_FIND_INDEX=3, SWR_PHP_KEYED_FIND_STRING=4,
    SWR_PHP_KEYED_APPEND=5, SWR_PHP_KEYED_PROMOTE_INDEX=6,
    SWR_PHP_KEYED_PROMOTE_STRING=7 };
/* Same lifecycle/observations as frozen merge; native numeric-key classification
 * precedes phase0. Rust selects API routes at the existing dispatch points. */
uint32_t swr_v1_phphelpers_merge_keyed(uint32_t *, uint8_t inserted,
                                    uint8_t existing_array, uint8_t numeric_key);
uint8_t swr_v1_phphelpers_call_success(int64_t result, uint8_t coroutine);
enum SwrPhpCallAction { SWR_PHP_CALL_NULL=0, SWR_PHP_CALL_DIRECT=1,
    SWR_PHP_CALL_COROUTINE=2, SWR_PHP_CALL_NAMED=3, SWR_PHP_CALL_RELEASE_NAME=4,
    SWR_PHP_CALL_OBSERVE_EXCEPTION=5, SWR_PHP_CALL_FATAL=6,
    SWR_PHP_CALL_TRUE=7, SWR_PHP_CALL_FALSE=8, SWR_PHP_CALL_VARIABLE=9 };
/* Phase0, modes direct0/coroutine1/named2. Native named-call allocation and local
 * Variable construction precede phase0; result and exception refreshed only after
 * invoke/observe actions. Native cleanup and fatal execution occur after return. */
uint32_t swr_v1_phphelpers_call_plan(uint32_t *, uint32_t mode, uint8_t has_retval,
                                   int64_t result, uint8_t exception);
enum SwrPhpCallableAction { SWR_PHP_CALLABLE_DONE=0, SWR_PHP_CALLABLE_TRUTH=1,
    SWR_PHP_CALLABLE_CHECK=2, SWR_PHP_CALLABLE_ILLEGAL=3,
    SWR_PHP_CALLABLE_INVALID=4, SWR_PHP_CALLABLE_RETAIN=5 };
uint32_t swr_v1_phphelpers_callable(uint32_t *, uint8_t truthy, uint8_t valid);
/* Copied kinds are module-local categories, never Zend ABI tags. */
enum SwrPhpKeyResult { SWR_PHP_KEY_OK=0, SWR_PHP_KEY_TYPE=1,
    SWR_PHP_KEY_RANGE=2, SWR_PHP_KEY_INVALID=3 };
/* Lazy typed-key policy: existing OK/TYPE/INVALID or request native index/count.
 * Only the latter may read Z_LVAL/hash count before the frozen key comparison. */
enum SwrPhpKeyRead { SWR_PHP_KEY_OBSERVE_INDEX=4 };
uint32_t swr_v1_phphelpers_key_route(uint32_t expected, uint32_t actual);
uint32_t swr_v1_phphelpers_key(uint32_t expected, uint32_t actual, int64_t key, uint32_t count);
enum SwrPhpValueResult { SWR_PHP_VALUE_OK=0, SWR_PHP_VALUE_TYPE=1,
    SWR_PHP_VALUE_OBJECT=2, SWR_PHP_VALUE_ARRAY=3 };
uint32_t swr_v1_phphelpers_value(uint32_t expected, uint32_t actual);
enum SwrPhpDefinitionAction { SWR_PHP_DEFINITION_FALSE=0, SWR_PHP_DEFINITION_TRUE=1,
    SWR_PHP_DEFINITION_TOO_LONG=2, SWR_PHP_DEFINITION_LOWERCASE=3,
    SWR_PHP_DEFINITION_NORMALIZE=4, SWR_PHP_DEFINITION_ENVELOPE=5,
    SWR_PHP_DEFINITION_SELF=6, SWR_PHP_DEFINITION_LOOKUP=7, SWR_PHP_DEFINITION_CLASS=8 };
/* Phase0 length is original Zend string length, data not read. Native lowercase
 * and normalization publish length/storage before phase2 reads initialized data.
 * SELF result/kind and LOOKUP result are fresh copied observations. Class result
 * is consumed while the native local zend::String remains alive for diagnostics. */
uint32_t swr_v1_phphelpers_parse_definition(uint32_t *, const uint8_t *, size_t length,
                                          uint32_t kind, uint8_t observation);
typedef struct SwrPhpBuiltinState { uint32_t phase; int32_t index; } SwrPhpBuiltinState;
enum SwrPhpBuiltinAction { SWR_PHP_BUILTIN_DONE=0, SWR_PHP_BUILTIN_TYPED=1,
    SWR_PHP_BUILTIN_CAPTURE_ARGUMENTS=2, SWR_PHP_BUILTIN_ARGUMENT=3,
    SWR_PHP_BUILTIN_REPLACEMENT=4, SWR_PHP_BUILTIN_REPLACEMENT_ARRAY=5,
    SWR_PHP_BUILTIN_REPLACEMENT_SCALAR=6, SWR_PHP_BUILTIN_SPLICE_SOURCE=7,
    SWR_PHP_BUILTIN_PUSH=8, SWR_PHP_BUILTIN_UNSHIFT=9,
    SWR_PHP_BUILTIN_SPLICE=10, SWR_PHP_BUILTIN_RESTORE=11 };
/* operation push0/unshift1/splice2. Native initial state{0,1}, argument count
 * observed before array inspection. Initial observation is array kind; later
 * observations belong only to TYPED/ARGUMENT/REPLACEMENT/check-replacement.
 * Native argument/HashTable custody and iteration/original execution retained. */
uint32_t swr_v1_phphelpers_builtin(SwrPhpBuiltinState *, uint32_t operation, int32_t count, uint8_t observation);
enum SwrPhpMutationAction { SWR_PHP_MUTATION_DONE=0, SWR_PHP_MUTATION_COPY_METADATA=1,
    SWR_PHP_MUTATION_ROUTE=2, SWR_PHP_MUTATION_INSERT=3,
    SWR_PHP_MUTATION_FETCH_W_CONST=4, SWR_PHP_MUTATION_FETCH_W_VAR=5,
    SWR_PHP_MUTATION_FETCH_RW_CONST=6, SWR_PHP_MUTATION_FETCH_RW_VAR=7,
    SWR_PHP_MUTATION_ASSIGN=8, SWR_PHP_MUTATION_CANNOT_ADD=9,
    SWR_PHP_MUTATION_REFERENCE=10, SWR_PHP_MUTATION_OPERATION=11,
    SWR_PHP_MUTATION_TYPED_REFERENCE=12, SWR_PHP_MUTATION_BINARY=13,
    SWR_PHP_MUTATION_CONCAT_ERROR=14, SWR_PHP_MUTATION_NUMERIC_ERROR=15,
    SWR_PHP_MUTATION_RETURN_USED=16, SWR_PHP_MUTATION_COPY_RESULT=17,
    SWR_PHP_MUTATION_IS_VAR=18, SWR_PHP_MUTATION_ADDREF=19,
    SWR_PHP_MUTATION_FREE=20, SWR_PHP_MUTATION_NULL=21 };
/* operation0 assign,1 compound-op; phase0 observation is post-COW source change.
 * Later observations: ROUTE null=1/constant=2/variable=3; engine pointer success;
 * REFERENCE nonref=0/untyped=1/typed=2; OPERATION copied kind|concat-bit256;
 * RETURN_USED/IS_VAR booleans. Native effects return before the next step.
 * FREE phase11 is failure cleanup before return observation/null; phase15 is
 * success cleanup (assignment debug tail follows it). Other facts are ignored. */
uint32_t swr_v1_phphelpers_mutation(uint32_t *, uint32_t operation, uint32_t observation);
enum SwrPhpValidationAction { SWR_PHP_VALIDATE_DONE=0, SWR_PHP_VALIDATE_TYPE=1,
    SWR_PHP_VALIDATE_OBJECT=2, SWR_PHP_VALIDATE_PLAIN_ARRAY=3,
    SWR_PHP_VALIDATE_ARRAY_TYPE=4, SWR_PHP_VALIDATE_INSTANCE=5,
    SWR_PHP_VALIDATE_ARRAY=6, SWR_PHP_VALIDATE_COMPARE=7 };
/* Phase0; observation only after INSTANCE/ARRAY/COMPARE completes natively.
 * Expected/actual are copied after native dereference. Error actions terminal. */
uint32_t swr_v1_phphelpers_validate_value(uint32_t *, uint32_t expected, uint32_t actual, uint8_t observation);
/* Comparisons over initialized metadata only; class/HashTable access native. */
uint8_t swr_v1_phphelpers_type_equal(uint32_t, uint32_t, uint32_t, uint32_t,
                                   const uint8_t *, size_t, const uint8_t *, size_t);
/* Normalization mutates only initialized native bytes. Host libc ctype/casefold
 * leaf functions preserve locale behavior; no Zend callback/effect in Rust. */
size_t swr_v1_phphelpers_compact(uint8_t *, size_t);
uint8_t swr_v1_phphelpers_envelope(const uint8_t *, size_t);
typedef struct SwrPhpTypeLayout { uint32_t key, value; uint16_t offset, length; } SwrPhpTypeLayout;
/* backing is initialized C-string bytes before its first NUL, logical is the
 * original uint16 logical type extent. Returns0 unsupported/native fallback,
 *1 layout,2 native key diagnostic; native writes fields in original order. */
uint32_t swr_v1_phphelpers_type_layout(const uint8_t *, size_t backing, uint16_t logical, SwrPhpTypeLayout *);
/* Initialized native span includes the first NUL and logical bytes plus their
 * next byte. Comma search stops at NUL while type classification uses the
 * logical extent, including initialized bytes after NUL. Same results and
 * publication plan as type_layout; unrepresented domains retain native fallback. */
uint32_t swr_v1_phphelpers_type_span(const uint8_t *, size_t backing, uint16_t logical, SwrPhpTypeLayout *);
/* expected kind and copied (opcode==ZEND_CONCAT). 0accepted,1string error,2numeric error. */
uint32_t swr_v1_phphelpers_operation(uint32_t, uint8_t concat);
/* Route native array/string/resource methods:0/1/2, other kinds dispatch=-1. */
int32_t swr_v1_phphelpers_method_family(uint32_t);
enum SwrPhpTypedAction { SWR_PHP_TYPED_DONE=0, SWR_PHP_TYPED_ALLOCATE=1,
    SWR_PHP_TYPED_PARSE=2, SWR_PHP_TYPED_FREE=3, SWR_PHP_TYPED_NULL=4,
    SWR_PHP_TYPED_INITIAL_TYPED=5, SWR_PHP_TYPED_COMPARE=6,
    SWR_PHP_TYPED_COPY_INITIAL=7, SWR_PHP_TYPED_MISMATCH=8, SWR_PHP_TYPED_CREATE=9,
    SWR_PHP_TYPED_PUBLISH=10, SWR_PHP_TYPED_NESTED=11, SWR_PHP_TYPED_ELEMENT=12,
    SWR_PHP_TYPED_DESTROY=13, SWR_PHP_TYPED_INITIAL=14, SWR_PHP_TYPED_ITERATE=15,
    SWR_PHP_TYPED_OBSERVE_TYPED=16, SWR_PHP_TYPED_DEFINITION=17,
    SWR_PHP_TYPED_TRUE=18, SWR_PHP_TYPED_FALSE=19, SWR_PHP_TYPED_SET_TRUE=20,
    SWR_PHP_TYPED_SET_FALSE=21, SWR_PHP_TYPED_STRING_KEY=22,
    SWR_PHP_TYPED_INDEX_KEY=23, SWR_PHP_TYPED_CHECK=24, SWR_PHP_TYPED_ADDREF=25,
    SWR_PHP_TYPED_INSERT_STRING=26, SWR_PHP_TYPED_INSERT_INDEX=27 };
/* Phase0, mode construction0/predicate1/initializer-entry2. Native parameter
 * parsing, authoritative metadata/HashTable and iterator custody remain native;
 * all observations fresh after their requested native effects. */
uint32_t swr_v1_phphelpers_typed(uint32_t *, uint32_t mode, uint8_t observation, uint8_t string_key);
enum SwrPhpInvocationAction { SWR_PHP_INVOKE_DONE=0, SWR_PHP_INVOKE_RESOLVE=1,
    SWR_PHP_INVOKE_UNKNOWN_METHOD=2, SWR_PHP_INVOKE_UNKNOWN_FUNCTION=3,
    SWR_PHP_INVOKE_ARGUMENTS=4, SWR_PHP_INVOKE_ALLOCATE=5, SWR_PHP_INVOKE_COPY=6,
    SWR_PHP_INVOKE_REORDER=7, SWR_PHP_INVOKE_CALL=8, SWR_PHP_INVOKE_OBSERVE=9,
    SWR_PHP_INVOKE_RELEASE_THIS=10, SWR_PHP_INVOKE_RELEASE_ARGUMENTS=11 };
/* Phase0; mode method0/reorder1. Alias/lookup/temporary-this observations are
 * consumed only at their phase. Native real_fn lexical string and scope guard
 * remain original; no Rust frame/borrow spans calls/destruction/cleanup. */
uint32_t swr_v1_phphelpers_invoke(uint32_t *, uint32_t mode, uint8_t observation);
typedef struct SwrPhpMethodState { uint32_t phase; int32_t family; } SwrPhpMethodState;
enum SwrPhpMethodAction { SWR_PHP_METHOD_DISPATCH=0, SWR_PHP_METHOD_CONTINUE=1,
    SWR_PHP_METHOD_CONSTANT=2, SWR_PHP_METHOD_VARIABLE=3, SWR_PHP_METHOD_OBSERVE=4,
    SWR_PHP_METHOD_REFERENCE=5, SWR_PHP_METHOD_ALLOCATE=6, SWR_PHP_METHOD_FILL=7,
    SWR_PHP_METHOD_ARRAY=8, SWR_PHP_METHOD_STRING=9, SWR_PHP_METHOD_STREAM=10,
    SWR_PHP_METHOD_PUBLISH=11 };
/* State{0,0}, operand constant0/unused1/variable2, copied kind including reference10.
 * Native object/reference and frame/CallInfo custody remain outside Rust. */
uint32_t swr_v1_phphelpers_method_frame(SwrPhpMethodState *, uint32_t operand, uint32_t observation);
enum SwrPhpVmAction { SWR_PHP_VM_DISPATCH=0, SWR_PHP_VM_CONTINUE=1,
    SWR_PHP_VM_ARRAY=2, SWR_PHP_VM_VARIABLE=3, SWR_PHP_VM_CONSTANT=4,
    SWR_PHP_VM_TEMPORARY=5, SWR_PHP_VM_DEREFERENCE=6, SWR_PHP_VM_OBSERVE_ARRAY=7,
    SWR_PHP_VM_OBSERVE_TYPED=8, SWR_PHP_VM_VALUE=9, SWR_PHP_VM_CONSTANT_KEY=10,
    SWR_PHP_VM_UNUSED_KEY=11, SWR_PHP_VM_VARIABLE_KEY=12, SWR_PHP_VM_CHECK=13,
    SWR_PHP_VM_INVOKE=14, SWR_PHP_VM_FREE=15, SWR_PHP_VM_ADVANCE=16,
    SWR_PHP_VM_LIST=17, SWR_PHP_VM_REFERENCE_ERROR=18, SWR_PHP_VM_LIST_ERROR=19 };
/* Phase0; operations assign0/reference-foreach1/unset2. Copied operand kind
 * variable1/constant2/temporary0, key constant0/unused1/variable2. Observation is
 * fresh native array/typed/list/check outcome only after its requested effect. */
uint32_t swr_v1_phphelpers_vm(uint32_t *, uint32_t operation, uint32_t operand,
                             uint32_t key, uint8_t observation);
/* operation assign=0,reference-foreach=1,unset=2; result dispatch=0,handle=1,
 * reference error=2,list deletion error=3. list fact used only by unset. */
uint32_t swr_v1_phphelpers_opcode(uint32_t, uint8_t typed, uint8_t list);
int64_t swr_v1_phphelpers_json_options(int64_t, int64_t mask, uint8_t assoc);
/* Exact pinned diagnostic definition projection into native uninitialized
 * writable storage; no allocator/callback. Value/output spans must be disjoint.
 * Native owns string allocation/publication; returns0 without writes if invalid. */
uint8_t swr_v1_phphelpers_definition(uint32_t key, const uint8_t *value, size_t value_length,
                                  uint8_t *output, size_t capacity, size_t *length);
#ifdef __cplusplus
}
#endif
#endif
