#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
namespace swoole { struct TableRow; struct TableColumn; struct TableIterator; class FixedPool; }
typedef swoole::TableRow swr_v1_memory_table_link;
typedef swoole::TableColumn swr_v1_memory_table_column_link;
typedef swoole::TableIterator swr_v1_memory_table_iterator_link;
typedef swoole::FixedPool swr_v1_memory_table_pool_link;
extern "C" {
#else
typedef struct swr_v1_memory_table_row swr_v1_memory_table_link;
typedef struct swr_v1_memory_table_column_opaque swr_v1_memory_table_column_link;
typedef struct swr_v1_memory_table_iterator_opaque swr_v1_memory_table_iterator_link;
typedef struct swr_v1_memory_table_pool_opaque swr_v1_memory_table_pool_link;
#endif
/* Single-use whole SharedMemory operation cursor. OS constants/results are
 * copied Native facts, never guessed Rust libc values or Native class objects.
 * phase0 starts; Native changes only memory/descriptor/result after each effect.
 * All effects run after return; state/output/live extents are disjoint. */
typedef struct swr_v2_memory_mapping_operation {
    size_t requested;
    uint8_t *source, *memory;
    size_t total;
    uint32_t kind, phase;
    int32_t flags, descriptor, result;
    uint32_t anonymous;
    int32_t anonymous_flags;
} swr_v2_memory_mapping_operation;
typedef struct swr_v2_memory_mapping_effect {
    void *memory;
    size_t size;
    int32_t descriptor, flags;
    uint32_t action;
    int32_t result;
} swr_v2_memory_mapping_effect;
enum swr_v2_memory_mapping_kind {
    SWR_MEMORY_MAPPING_ALLOCATE=0, SWR_MEMORY_MAPPING_RELEASE=1,
    SWR_MEMORY_MAPPING_PROTECT=2, SWR_MEMORY_MAPPING_REALLOCATE=3
};
enum swr_v2_memory_mapping_action {
    SWR_MEMORY_MAPPING_OPEN=1, SWR_MEMORY_MAPPING_MAP=2,
    SWR_MEMORY_MAPPING_WARN_ALLOCATE=3, SWR_MEMORY_MAPPING_UNMAP=4,
    SWR_MEMORY_MAPPING_WARN_RELEASE=5, SWR_MEMORY_MAPPING_SET_PROTECTION=6,
    SWR_MEMORY_MAPPING_INVALID_PROTECTION=7,
    SWR_MEMORY_MAPPING_ALLOCATE_PAYLOAD=8, SWR_MEMORY_MAPPING_RELEASE_NEW_PAYLOAD=9,
    SWR_MEMORY_MAPPING_RELEASE_OLD_PAYLOAD=10
};
/*1 requests the action,0 completes (memory/result),-1 rejects control/header.
 * Existing mapping_size/product/initialize/extent/relocate contracts remain. */
int32_t swr_v2_memory_mapping_step(swr_v2_memory_mapping_operation *, swr_v2_memory_mapping_effect *);

/* Borrowed C PODs; no callback, destructor or allocation callback enters Rust. */
typedef struct swr_v1_memory_fixed_slice {
    uint8_t lock;
    struct swr_v1_memory_fixed_slice *next, *prev;
} swr_v1_memory_fixed_slice;
typedef struct swr_v1_memory_fixed {
    void *memory;
    size_t size;
    swr_v1_memory_fixed_slice *head, *tail;
    uint32_t slice_num, slice_use, slice_size;
    uint8_t shared, allocated;
} swr_v1_memory_fixed;
typedef struct swr_v1_memory_fixed_layout_result {
    size_t total, usable;
    uint32_t slices, width;
} swr_v1_memory_fixed_layout_result;
/* owned=1: count>=2, available=0, width rounded to8. owned=0: count=0,
 * available is the borrowed arena length, original odd widths retained. */
int32_t swr_v1_memory_fixed_layout(uint32_t count, uint32_t width, size_t available,
                                 uint32_t owned, swr_v1_memory_fixed_layout_result *);
/* Serialized read-only pool snapshot; output is independent/disjoint. Spare
 * subtraction preserves defined unsigned wrap; actual public widths unchanged. */
typedef struct swr_v1_memory_fixed_usage_result { uint32_t spare, total, width; } swr_v1_memory_fixed_usage_result;
int32_t swr_v1_memory_fixed_usage(const swr_v1_memory_fixed *, swr_v1_memory_fixed_usage_result *);
/* Native executes the returned ownership action after Rust returns:
 *0 borrowed/no effect,1/2 heap/shared allocation,3/4 heap/shared free,-1 invalid.
 * Used by actual FixedPool and RingBuffer constructors/rollback/destructors. */
int32_t swr_v1_memory_arena_lifecycle(uint32_t shared, uint32_t owned, uint32_t phase);
/* Independent serialized debug cursor/output; no C++ object or native callback.
 * Cursor starts zero; step1 emits a record,0 ends,-1 rejects. max0 emits2 as pin.
 * Live arena links remain valid throughout traversal; output/cursor disjoint. */
typedef struct swr_v1_memory_fixed_debug_cursor {
    swr_v1_memory_fixed_slice *next;
    uint64_t line;
} swr_v1_memory_fixed_debug_cursor;
typedef struct swr_v1_memory_fixed_debug_record {
    swr_v1_memory_fixed_slice *slice, *prev, *next;
    uint8_t *data;
    uint64_t line;
    uint8_t lock, self_link;
} swr_v1_memory_fixed_debug_record;
int32_t swr_v1_memory_fixed_debug_step(const swr_v1_memory_fixed *, swr_v1_memory_fixed_debug_cursor *,
                                      int32_t max_lines, swr_v1_memory_fixed_debug_record *);
/* Separate immutable plan; exclusive arena covers its complete total bytes. */
int32_t swr_v1_memory_fixed_construct(swr_v1_memory_fixed *, const swr_v1_memory_fixed_layout_result *,
                                    uint32_t shared, uint32_t owned);
int32_t swr_v1_memory_fixed_init(swr_v1_memory_fixed *);
void *swr_v1_memory_fixed_alloc(swr_v1_memory_fixed *);
int32_t swr_v1_memory_fixed_free(swr_v1_memory_fixed *, void *);
/* Independent channel state snapshot; no C++ class, lock or pipe crosses Rust. */
typedef struct swr_v1_memory_channel {
    int64_t head, tail;
    size_t size;
    uint8_t head_tag, tail_tag;
    int32_t num, max_num;
    size_t bytes;
    int32_t flags, maxlen;
    void *mem;
} swr_v1_memory_channel;
int32_t swr_v1_memory_channel_in(swr_v1_memory_channel *, const void *, int32_t);
int32_t swr_v1_memory_channel_out(swr_v1_memory_channel *, void *, int32_t, uint32_t consume);
/* Independent typed field addresses, obtained by native member access. Targets
 * are disjoint, live, aligned, serialized and initialized (except during init).
 * Descriptor/plan/payload are disjoint. No C++ class, lock or pipe is borrowed. */
typedef struct swr_v1_memory_channel_fields {
    int64_t *head, *tail;
    size_t *size;
    char *head_tag, *tail_tag;
    int32_t *num, *max_num;
    size_t *bytes;
    int32_t *flags, *maxlen;
    void **mem;
} swr_v1_memory_channel_fields;
typedef struct swr_v1_memory_channel_plan {
    size_t total, size, header_size;
    int32_t maxlen, flags;
} swr_v1_memory_channel_plan;
int32_t swr_v1_memory_channel_storage_plan(size_t, size_t, int32_t, size_t, swr_v1_memory_channel_plan *);
int32_t swr_v1_memory_channel_storage_init(const swr_v1_memory_channel_fields *, const swr_v1_memory_channel_plan *, void *);
int32_t swr_v1_memory_channel_storage_in(const swr_v1_memory_channel_fields *, const void *, int32_t);
int32_t swr_v1_memory_channel_storage_out(const swr_v1_memory_channel_fields *, void *, int32_t);
/* Independent read-only scalars for full(); unsigned occupancy wraps as C++. */
typedef struct swr_v1_memory_channel_capacity {
    int64_t head, tail;
    size_t size, bytes;
    int32_t num;
    uint8_t head_tag, tail_tag;
} swr_v1_memory_channel_capacity;
int32_t swr_v1_memory_channel_full(const swr_v1_memory_channel_capacity *);
enum swr_v1_memory_channel_action {
    SWR_CHANNEL_ALLOC_HEAP = 1, SWR_CHANNEL_ALLOC_SHARED = 2, SWR_CHANNEL_INITIALIZE = 3,
    SWR_CHANNEL_CREATE_LOCK = 4, SWR_CHANNEL_CREATE_PIPE = 5, SWR_CHANNEL_DELETE_LOCK = 6,
    SWR_CHANNEL_DELETE_PIPE = 7, SWR_CHANNEL_FREE_HEAP = 8, SWR_CHANNEL_FREE_SHARED = 9
};
typedef struct swr_v1_memory_channel_lifecycle_result {
    uint32_t count, actions[4];
} swr_v1_memory_channel_lifecycle_result;
/* phase0: constructor effects, phase1: teardown effects, in native execution order. */
int32_t swr_v1_memory_channel_lifecycle(int32_t flags, uint32_t phase, swr_v1_memory_channel_lifecycle_result *);
/* Rust-owned opaque heap; public node POD layout stays unchanged. */
typedef struct swr_v1_memory_heap_node {
    uint64_t priority;
    uint32_t position;
    void *data;
} swr_v1_memory_heap_node;
/* Independent snapshot and index; serialized with heap mutations. Each step
 * copies one live node and advances index in Rust; terminal output is cleared.
 *1 record,0 end,-1 invalid; native printf executes only after return. */
int32_t swr_v1_memory_heap_debug_step(const void *, size_t *, swr_v1_memory_heap_node *);
int32_t swr_v1_memory_heap_create(size_t capacity, uint32_t max, void **);
void swr_v1_memory_heap_release(void *);
size_t swr_v1_memory_heap_count(const void *);
swr_v1_memory_heap_node *swr_v1_memory_heap_at(const void *, size_t index);
int32_t swr_v1_memory_heap_compare(const void *, uint64_t a, uint64_t b);
swr_v1_memory_heap_node *swr_v1_memory_heap_push(void *, uint64_t, void *);
int32_t swr_v1_memory_heap_update(void *, uint64_t, swr_v1_memory_heap_node *);
int32_t swr_v1_memory_heap_remove(void *, swr_v1_memory_heap_node *);
void *swr_v1_memory_heap_pop(void *);
/* Rust-owned page registry/configuration. Native performs page/mutex/getpid and
 * wrapper effects after return; inherited shared pages remain attached on reset. */
typedef struct swr_v1_memory_global_effect {
    void *page;
    uint32_t page_size, aligned, action;
} swr_v1_memory_global_effect;
enum swr_v1_memory_global_action {
    SWR_GLOBAL_ALLOC_HEAP = 1, SWR_GLOBAL_ALLOC_SHARED = 2,
    SWR_GLOBAL_FREE_HEAP = 3, SWR_GLOBAL_FREE_SHARED = 4, SWR_GLOBAL_RESET_SHARED = 5
};
/* open: -2 invalid config, -1 allocation failure,0 success; shared is0/1.
 * Outputs/descriptors disjoint from registry/pages; calls serialized by native.
 * phase0 allocation plan; phase1 validates requested before owner/reset choice;
 * phase2 drains one page in insertion order, action0 means no pages remain.
 * Native executes each free before next drain; release only after full drain.
 * No Rust reference survives a page effect or native wrapper replacement. */
int32_t swr_v1_memory_global_open(uint32_t requested, uint32_t system_page, uint32_t shared,
                                  int64_t creator, void **);
int32_t swr_v1_memory_global_step(void *, uint32_t phase, int64_t current, uint32_t requested,
                                  swr_v1_memory_global_effect *);
int32_t swr_v1_memory_global_page_size(uint32_t requested, uint32_t system_page, uint32_t *);
int32_t swr_v1_memory_global_request_valid(const void *, uint32_t requested, uint32_t *aligned);
int32_t swr_v1_memory_global_create(uint32_t page_size, void **);
int32_t swr_v1_memory_global_add_page(void *, void *page);
int32_t swr_v1_memory_global_alloc(void *, uint32_t size, void **);
size_t swr_v1_memory_global_capacity(const void *);
size_t swr_v1_memory_global_memory_size(const void *);
void *swr_v1_memory_global_pop_page(void *);
int32_t swr_v1_memory_global_release(void *);
/* Producer-only snapshot. Atomic slot/header synchronization is shared. */
typedef struct swr_v1_memory_ring {
    void *memory;
    uint32_t size, alloc_offset, collect_offset, alloc_count;
    uint8_t status;
    uint32_t *free_count;
} swr_v1_memory_ring;
int32_t swr_v1_memory_ring_layout(uint32_t requested, uint32_t *total, uint32_t *payload);
void *swr_v1_memory_ring_alloc(swr_v1_memory_ring *, uint32_t requested);
int32_t swr_v1_memory_ring_free(void *memory, uint32_t size, uint32_t *free_count, void *data);
/* Actual shared arena POD base; no C++ class layout or mutable whole-header
 * reference crosses Rust. Producer fields and atomic counter are separate. */
typedef struct swr_v1_memory_ring_storage {
    void *memory;
    uint8_t shared, status;
    uint32_t size, alloc_offset, collect_offset, alloc_count;
    volatile uint32_t free_count;
} swr_v1_memory_ring_storage;
/* Fresh exclusive total-byte arena, before any producer/consumer publication. */
int32_t swr_v1_memory_ring_construct(swr_v1_memory_ring_storage *, uint32_t total, uint32_t shared);
void *swr_v1_memory_ring_storage_alloc(swr_v1_memory_ring_storage *, uint32_t);
/* Checked native shared-mapping byte plans, including the8-byte header. */
typedef struct swr_v1_memory_mapping_extent_result {
    void *base;
    size_t total;
} swr_v1_memory_mapping_extent_result;
/* Native supplies live mapping storage; actual 8-byte header remains in arena.
 * Outputs are separate exclusive PODs. Relocation requires disjoint mappings. */
void *swr_v1_memory_mapping_initialize(void *base, size_t total);
int32_t swr_v1_memory_mapping_extent(const void *payload, swr_v1_memory_mapping_extent_result *);
int32_t swr_v1_memory_mapping_relocate(const void *old, void *new_);
int32_t swr_v1_memory_mapping_size(size_t requested, size_t *total);
int32_t swr_v1_memory_mapping_product(size_t count, size_t width, size_t *requested);
int32_t swr_v1_memory_mapping_copy(size_t old_total, size_t new_total, size_t *bytes);
/* Actual C POD row storage; C++ TableRow derives without data members.
 * Locking and hash callbacks remain native. All row byte access is unaligned. */
typedef struct swr_v1_memory_table_row {
    volatile uint32_t lock_;
    int32_t lock_pid;
    uint8_t active, key_len;
    swr_v1_memory_table_link *next;
    char key[64];
    char data[0];
} swr_v1_memory_table_row;
typedef struct swr_v1_memory_table_plan {
    void *row, *parent;
    uint32_t level, flags, initialize;
} swr_v1_memory_table_plan;
/* Live typed counter targets; descriptor/state are independent of actual fields.
 * Native accesses are atomic/serialized; key/row lifetimes follow each phase. */
typedef struct swr_v1_memory_table_counter_fields {
    volatile uint32_t *rows;
    volatile int64_t *inserted, *deleted, *updated;
    size_t *conflicts;
    uint32_t *max_conflict;
} swr_v1_memory_table_counter_fields;
typedef struct swr_v1_memory_table_mutation {
    swr_v1_memory_table_counter_fields counters;
    swr_v1_memory_table_link *root, *row, *removed;
    const uint8_t *key;
    int32_t *out_flags;
    size_t item_size;
    swr_v1_memory_table_plan plan;
    uint32_t mode, phase;
    uint16_t key_length;
} swr_v1_memory_table_mutation;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_counter_fields) == 48 && sizeof(swr_v1_memory_table_mutation) == 144,
              "table mutation independent POD ABI");
#endif
/* mode0 set/mode1 delete; phase initially0. Return1: native pool effect, then
 * resume Rust phase1. Set supplies row; delete frees removed before resuming.
 * Return0 success,2 missing delete,-1 invalid; phase2 completed cannot resume. */
int32_t swr_v1_memory_table_mutation_step(swr_v1_memory_table_mutation *);
/* Independent field view, exclusive under iterator mutex. Current buffer and
 * scalar targets/descriptors/lookup are disjoint. Row lookup and locking occur
 * only after Rust returns; non-NULL root must be locked for phase1. */
typedef struct swr_v1_memory_table_iterator_fields {
    uint32_t *absolute, *collision;
    swr_v1_memory_table_link *current;
    size_t row_size;
} swr_v1_memory_table_iterator_fields;
int32_t swr_v1_memory_table_iterator_reset(const swr_v1_memory_table_iterator_fields *);
int32_t swr_v1_memory_table_iterator_step(const swr_v1_memory_table_iterator_fields *, size_t buckets,
                                        swr_v1_memory_table_link *root, uint32_t phase, uint32_t *lookup);
typedef struct swr_v1_memory_table_layout_result {
    size_t total, row_size, pool_offset, pool_size;
    uint32_t rows;
} swr_v1_memory_table_layout_result;
/* Read-only live row-pointer span, not a C++ Table/row object borrow. Cursor
 * independent, serialized with Table destruction. phase0 normalizes key length
 * (return1); native invokes HashFunc after return and fills hash only; phase1
 * selects pointer token (return0). Invalid/replay -1. Caller keeps key buffer
 * live for normalized prefix; no Rust borrow/frame crosses native callback.
 * Row locking/prelock activity observation remain native and unchanged. */
typedef struct swr_v1_memory_table_lookup {
    swr_v1_memory_table_link *const *rows;
    size_t count, mask;
    uint64_t hash;
    size_t index;
    swr_v1_memory_table_link *row;
    uint16_t length;
    uint32_t phase;
} swr_v1_memory_table_lookup;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_lookup) == 56, "independent table lookup ABI");
#endif
int32_t swr_v1_memory_table_lookup_step(swr_v1_memory_table_lookup *);
/* Borrowed name remains live through insertion; cursor, item-size and column
 * scalar targets disjoint/aligned, serialized and live throughout each phase.
 * No C++ object borrow; opaque column token never dereferenced by Rust.
 * phase0->1 native column construction; phase1->2 native vector append;
 * phase2 returns0 commit or3 native pop-back rollback before RAII column delete.
 * -2 unknown type requests native warning, -1 invalid/pre-effect failure.
 * Native effect must finish before resume; no restart/replay after partial effect. */
typedef struct swr_v1_memory_table_declaration {
    void *index;
    size_t *item_size;
    const uint8_t *name;
    size_t length, requested, base, next;
    void *column;
    size_t *column_index;
    uint32_t *column_width;
    uint32_t kind, width, phase;
} swr_v1_memory_table_declaration;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_declaration) == 96, "independent column declaration ABI");
#endif
int32_t swr_v1_memory_table_declaration_step(swr_v1_memory_table_declaration *);
/* Disjoint aligned actual field targets; no C++ class borrow. Initialization
 * requires fresh unpublished storage, creation exclusive serialization. created
 * points to one native bool object-representation byte, only0/1 is written. */
typedef struct swr_v1_memory_table_metadata_fields {
    size_t *size, *mask, *item_size, *memory_size;
    float *conflict;
    uint8_t *created;
    swr_v1_memory_table_link ***rows;
    swr_v1_memory_table_pool_link **pool;
    swr_v1_memory_table_iterator_link **iterator;
    void **memory;
    swr_v1_memory_table_counter_fields counters;
} swr_v1_memory_table_metadata_fields;
typedef struct swr_v1_memory_table_creation {
    swr_v1_memory_table_layout_result logical, physical;
    void *memory, *pool, *iterator;
    uint32_t phase;
} swr_v1_memory_table_creation;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_metadata_fields) == 128 && sizeof(swr_v1_memory_table_creation) == 112,
              "independent Table metadata/publication ABI");
#endif
/* initialize validates before writes, zeros actual unpublished metadata/counters.
 * Creation phase0 ->1 requests native effects; phase1 validates unchanged plans
 * and live tokens then publishes fields/created and returns0. Other states -1.
 * Native retains arena/pool/iterator RAII until successful publication; no
 * borrow/callback enters Rust. Plans/cursor/targets and live arena are disjoint. */
int32_t swr_v1_memory_table_metadata_initialize(const swr_v1_memory_table_metadata_fields *, uint32_t, float);
int32_t swr_v1_memory_table_creation_step(const swr_v1_memory_table_metadata_fields *, swr_v1_memory_table_creation *);
/* Complete construction transaction, independent of frozen creation ABI.
 * Zero cursor starts.1 requests effect,0 publishes all fields/created,-1 invalid.
 * Actions:1 allocate shared arena(size);2 construct native FixedPool(row_size,
 * memory,size,true);3 construct native TableIterator(size). Native records the
 * resulting tokens in storage.memory/pool/iterator before resume and retains
 * RAII until return0. Rust initializes arena rows and computes the pool interior
 * pointer; no class/allocator/effect is called or borrowed through Rust.
 * Scratch/targets/arena disjoint; exclusive schema serialization; no restart or
 * reuse after error, native exception or completion. Existing native exception
 * propagation/RAII remains outside Rust. This is not allocator-failure proof. */
typedef struct swr_v1_memory_table_construction {
    swr_v1_memory_table_creation storage;
    uint32_t phase;
} swr_v1_memory_table_construction;
typedef struct swr_v1_memory_table_construction_effect {
    void *memory;
    size_t size, row_size;
    uint32_t action;
} swr_v1_memory_table_construction_effect;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_construction) == 120 &&
              sizeof(swr_v1_memory_table_construction_effect) == 32, "table construction ABI");
#endif
int32_t swr_v1_memory_table_construction_step(const swr_v1_memory_table_metadata_fields *,
    swr_v1_memory_table_construction *, swr_v1_memory_table_construction_effect *);
/* Unpublished Table factory: rows/conflict/legacy input, other fields zero.
 * Positive return requests1 native Table allocation,2 native Mutex(true),
 *3 native legacy vector; caller records tokens before resume. fields may be NULL
 * until final resume; then fresh unpublished actual targets are required.
 *0 commits normalized metadata and optional sole Rust name index. Native
 * publishes mutex/list/index/hash only after0 and transfers RAII custody.
 * -1 leaves native rollback with caller; exceptions/effects stay native, no
 * restart or reuse, externally serialized, no allocation-failure qualification.
 * Legacy0 allocates no vector/index; legacy1 preserves public vector ABI. */
typedef struct swr_v1_memory_table_factory {
    void *table, *mutex, *list, *index;
    uint32_t rows;
    float conflict;
    uint32_t legacy, phase;
} swr_v1_memory_table_factory;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_factory) == 48, "table factory ABI");
#endif
int32_t swr_v1_memory_table_factory_step(const swr_v1_memory_table_metadata_fields *, swr_v1_memory_table_factory *);
int32_t swr_v1_memory_table_config(uint32_t, float, uint32_t *, float *);
int32_t swr_v1_memory_table_layout(uint32_t, size_t, float, swr_v1_memory_table_layout_result *);
/* Additive physical plan rounds record strides to frozen row alignment.
 * Existing layout remains the logical/accounting plan with unchanged outputs. */
int32_t swr_v1_memory_table_storage_layout(uint32_t, size_t, float, swr_v1_memory_table_layout_result *);
int32_t swr_v1_memory_table_arena(void *, const swr_v1_memory_table_layout_result *);
int32_t swr_v1_memory_table_clear(swr_v1_memory_table_row *, uint32_t keep_lock);
int32_t swr_v1_memory_table_init(swr_v1_memory_table_row *, const uint8_t *, uint16_t);
swr_v1_memory_table_row *swr_v1_memory_table_get(swr_v1_memory_table_row *, const uint8_t *, uint16_t);
int32_t swr_v1_memory_table_set_plan(swr_v1_memory_table_row *, const uint8_t *, uint16_t, swr_v1_memory_table_plan *);
int32_t swr_v1_memory_table_delete(swr_v1_memory_table_row *, const uint8_t *, uint16_t, size_t, void **);
int32_t swr_v1_memory_table_next(swr_v1_memory_table_row *, uint32_t, swr_v1_memory_table_row *, size_t, uint32_t *, uint32_t *);
int32_t swr_v1_memory_table_column_size(uint32_t, size_t, uint32_t *);
int32_t swr_v1_memory_table_clear_value(swr_v1_memory_table_row *, size_t, uint32_t, uint32_t);
int32_t swr_v1_memory_table_set_value(swr_v1_memory_table_row *, size_t, uint32_t, uint32_t, const void *, size_t);
int32_t swr_v1_memory_table_get_number(const swr_v1_memory_table_row *, size_t, void *);
int32_t swr_v1_memory_table_get_string(const swr_v1_memory_table_row *, size_t, uint32_t, uint8_t **, uint32_t *);
/* Teardown borrows only the live pointer-token array from public vector.data(),
 * never the C++ vector object. The vector is unchanged until its delete action;
 * distinct column objects with duplicate names retain declaration order.
 * Cursor/output independent of Table/array/arena; calls exclusively serialized.
 * phase starts0;1 effect,0 complete,-1 invalid. Native executes action before
 * resuming:1 column delete,2 vector delete,3 iterator delete,4 pool delete,
 *5 shared arena release,6 mutex delete,7 Table memory-pool release.
 * Index disposal and actual memory=NULL publication are Rust; native class
 * destructors/free run only after return. After final release only cursor is
 * accessed. No reuse after partial native effect failure or phase restart. */
typedef struct swr_v1_memory_table_teardown {
    void *index;
    swr_v1_memory_table_column_link *const *columns;
    size_t count, position;
    void *list, *iterator, *pool;
    void **memory;
    void *mutex, *table;
    uint32_t phase;
} swr_v1_memory_table_teardown;
typedef struct swr_v1_memory_table_teardown_effect {
    void *token;
    uint32_t action;
} swr_v1_memory_table_teardown_effect;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_teardown) == 88 && sizeof(swr_v1_memory_table_teardown_effect) == 16,
              "independent table teardown ABI");
#endif
int32_t swr_v1_memory_table_teardown_step(swr_v1_memory_table_teardown *, swr_v1_memory_table_teardown_effect *);
/* Actual collection-free TableV2 core only: index/columns/list/count/position
 * stay null/zero, and phase0 selects row/iterator/pool/arena/mutex/core cleanup.
 * All existing teardown signatures/layouts and legacy behavior stay unchanged.
 * Effects complete natively after return; terminal resume reads scratch only. */
int32_t swr_v1_memory_table_core_teardown_step(swr_v1_memory_table_teardown *, swr_v1_memory_table_teardown_effect *);
/* Independent copied destruction tokens. phase0 starts;1 effect,0 terminal,
 * -1 invalid. action1 sw_free(current), action2 delete native Mutex. Native
 * completes each effect and refreshes mutex token from actual field before
 * resume; no Rust borrow spans native allocation
 * callback/destruction. Null current skips free (custom allocator not called);
 * null mutex still receives native delete-null effect. No restart/partial retry. */
typedef struct swr_v1_memory_table_iterator_release {
    void *current, *mutex;
    uint32_t phase;
} swr_v1_memory_table_iterator_release;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_iterator_release) == 24, "iterator release ABI");
#endif
int32_t swr_v1_memory_table_iterator_release_step(swr_v1_memory_table_iterator_release *, swr_v1_memory_table_teardown_effect *);
/* Cursor/row/value disjoint and live, serialized through native warning effect.
 * phase0 returns0 after write, or1 requests native warning BEFORE any row write.
 * Native completes warning, may refresh descriptor scalar facts, then resumes
 * phase1 to write. Existing truncation/null-string policy unchanged. Terminal
 * replay -1 before touching value/row; no Rust frame spans warning/bailout. */
typedef struct swr_v1_memory_table_value {
    swr_v1_memory_table_row *row;
    const void *value;
    size_t length, index;
    uint32_t width, kind, phase;
} swr_v1_memory_table_value;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_value) == 48, "table value ABI");
#endif
int32_t swr_v1_memory_table_value_step(swr_v1_memory_table_value *);
/* Per-call POD snapshot; native TableColumn objects stay native and mutable. */
typedef struct {
    size_t index;
    uint32_t width;
    uint32_t kind;
} swr_v1_memory_table_column;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_column) == 16 &&
              offsetof(swr_v1_memory_table_column, width) == 8 &&
              offsetof(swr_v1_memory_table_column, kind) == 12, "column snapshot ABI");
#endif
/* Live pointer-token span and row remain serialized/live through completion.
 * Independent cursor/snapshots disjoint from row/span/native column objects.
 * phase0 starts, return1 requests exactly take native descriptor field copies
 * into batch[] from tokens[]; native must not change cursor control fields.
 * Resume clears validated batch and requests next or returns0. -1 invalid,
 * terminal failure cannot restart. Earlier batches remain committed on failure.
 * Native vector custody/mutable column layout stay native; no callback/frame
 * crosses Rust. Empty list completes without touching row. */
typedef struct swr_v1_memory_table_clear_cursor {
    swr_v1_memory_table_row *row;
    swr_v1_memory_table_column_link *const *columns;
    size_t count, position, item_size;
    swr_v1_memory_table_column_link *tokens[8];
    swr_v1_memory_table_column batch[8];
    uint32_t take, phase;
} swr_v1_memory_table_clear_cursor;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_table_clear_cursor) == 240, "independent clear cursor ABI");
#endif
int32_t swr_v1_memory_table_clear_step(swr_v1_memory_table_clear_cursor *);
int32_t swr_v1_memory_table_clear_columns(swr_v1_memory_table_row *, const swr_v1_memory_table_column *, size_t, size_t);
/* Rust-owned byte-key index; native column tokens are never dereferenced. */
int32_t swr_v1_memory_table_columns_create(void **);
int32_t swr_v1_memory_table_columns_insert(void *, const uint8_t *, size_t, void *);
void *swr_v1_memory_table_columns_get(const void *, const uint8_t *, size_t);
size_t swr_v1_memory_table_columns_count(const void *);
void *swr_v1_memory_table_columns_pop(void *);
int32_t swr_v1_memory_table_columns_release(void *);
/* Consume a borrowed index; native code retains custody of every column token. */
int32_t swr_v1_memory_table_columns_discard(void *);
/* Versioned sole ordered-column owner for TableV2. Legacy Table/Columns APIs
 * remain distinct. Every opaque native column token is owned once by this store;
 * first duplicate-name lookup and all declaration-order tokens are retained.
 * No native vector mirrors this store. Native column effects occur after return. */
typedef struct swr_v1_memory_columns_v2 swr_v1_memory_columns_v2;
typedef struct swr_v1_memory_columns_v2_declaration {
    swr_v1_memory_columns_v2 *owner;
    size_t *item_size;
    const uint8_t *created, *name;
    size_t length, requested, base, next;
    void *column;
    size_t *column_index;
    const uint32_t *column_width;
    uint32_t kind, width, phase;
} swr_v1_memory_columns_v2_declaration;
typedef struct swr_v1_memory_columns_v2_cursor {
    size_t count, unique_count, position;
    uint64_t generation;
    swr_v1_memory_table_column_link *column;
} swr_v1_memory_columns_v2_cursor;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_columns_v2_declaration) == 104 &&
              sizeof(swr_v1_memory_columns_v2_cursor) == 40, "owned columns v2 ABI");
#endif
/* Targets/borrowed name/cursors/owner disjoint, aligned and live. Mutation,
 * creation and close require exclusive serialization; sealed-owner lookup and
 * cursor reads may concur with independent scratch. Clear may share sealed
 * owner with independently locked/disjoint rows; no column metadata mutation.
 * open0/-1, output null on failure. Declare phase0 returns1 native construction;
 * phase1 reserves all storage then publishes index/width/custody (0), or-1 with
 * native RAII custody retained. -2 unknown type requests native warning. No
 * restart after native effect; created!=0 refuses before construction. */
int32_t swr_v1_memory_columns_v2_open(swr_v1_memory_columns_v2 **);
int32_t swr_v1_memory_columns_v2_declare_step(swr_v1_memory_columns_v2_declaration *);
void *swr_v1_memory_columns_v2_get(const swr_v1_memory_columns_v2 *, const uint8_t *, size_t);
/* Scratch cursor only: open0/-1; next1 token,0 end,-1 closing/generation change.
 * No owner borrow spans native/Zend effects; native token lifetime requires
 * owner/column to remain live. Count includes duplicates; unique_count does not.
 * Errors must remain distinct from an empty list in callers. */
int32_t swr_v1_memory_columns_v2_cursor_open(const swr_v1_memory_columns_v2 *, swr_v1_memory_columns_v2_cursor *);
int32_t swr_v1_memory_columns_v2_cursor_next(const swr_v1_memory_columns_v2 *, swr_v1_memory_columns_v2_cursor *);
/* Uses existing clear cursor protocol, sets count from actual Rust store and
 * selects tokens; never exposes native vector or retained Rust-vector pointer. */
int32_t swr_v1_memory_columns_v2_clear_step(const swr_v1_memory_columns_v2 *, swr_v1_memory_table_clear_cursor *);
/* Actual typed owner field is nulled on final completion.1 transfers one column
 * token to native delete;0 releases Rust index/vector and nulls field;-1 invalid.
 * Null owner is an empty cleanup, no allocation/callback. Caller completes each
 * native deletion before resume. No lookup/mutation/cursor after closing starts,
 * no restart or use after final free; terminal null-field cleanup is harmless. */
int32_t swr_v1_memory_columns_v2_close_step(swr_v1_memory_columns_v2 **, void **);
/* Authoritative Rust metadata owner used by the amended TableV2 facade.
 * Original token-owner declarations above stay ABI-compatible and distinct.
 * Owner/cursor/view/field/buffer disjoint, aligned, live; mutations/close
 * exclusive, sealed reads may share independent scratch. No Rust span escapes.
 * Views valid only while owner lives and generation is unchanged. Not-found0
 * is distinct from error-1; get/next success1; other success0. Unknown kind-2.
 * Declare reserves all fallible storage before committing actual item_size.
 * Copy validates the entire descriptor before writing name_length bytes; caller
 * owns scratch through any native/Zend effects. Close nulls the actual field,
 * drops all records/name bytes without callbacks, and is null-idempotent. */
typedef struct swr_v1_memory_records swr_v1_memory_records;
typedef struct swr_v1_memory_record_view {
    size_t ordinal;
    uint64_t generation;
    size_t index, name_length;
    uint32_t width, kind;
} swr_v1_memory_record_view;
typedef struct swr_v1_memory_record_cursor {
    size_t count, unique_count, position;
    uint64_t generation;
} swr_v1_memory_record_cursor;
#ifdef __cplusplus
static_assert(sizeof(swr_v1_memory_record_view) == 40 && sizeof(swr_v1_memory_record_cursor) == 32,
              "copied metadata record ABI");
#endif
int32_t swr_v1_memory_records_open(swr_v1_memory_records **);
int32_t swr_v1_memory_records_declare(swr_v1_memory_records *, size_t *, const uint8_t *, const uint8_t *, size_t, uint32_t, size_t);
int32_t swr_v1_memory_records_get(const swr_v1_memory_records *, const uint8_t *, size_t, swr_v1_memory_record_view *);
int32_t swr_v1_memory_records_cursor_open(const swr_v1_memory_records *, swr_v1_memory_record_cursor *);
int32_t swr_v1_memory_records_cursor_next(const swr_v1_memory_records *, swr_v1_memory_record_cursor *, swr_v1_memory_record_view *);
int32_t swr_v1_memory_records_copy_name(const swr_v1_memory_records *, const swr_v1_memory_record_view *, uint8_t *, size_t);
int32_t swr_v1_memory_records_clear(const swr_v1_memory_records *, swr_v1_memory_table_row *);
int32_t swr_v1_memory_records_close(swr_v1_memory_records **);
#ifdef __cplusplus
}
#endif
