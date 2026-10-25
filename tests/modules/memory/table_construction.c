/* Pure construction-effect model. No Swoole allocator/mutex/IPC is executed. */
#include "swoole_rs_memory.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    size_t cases = 0;
    assert(sizeof(swr_v1_memory_table_construction) == 120);
    assert(sizeof(swr_v1_memory_table_construction_effect) == 32);
    for (uint32_t requested = 64; requested <= 256; requested *= 2) {
        for (size_t item = 8; item <= 24; item += 8) {
            for (unsigned ratio = 0; ratio < 3; ratio++) {
                const float proportions[] = {0.2f, 0.5f, 1.0f};
                size_t size, mask, item_size, memory_size, conflicts = 0;
                uint32_t count = 0;
                float proportion;
                uint8_t created;
                swr_v1_memory_table_row **rows;
                swr_v1_memory_table_pool_link *pool;
                swr_v1_memory_table_iterator_link *iterator;
                void *memory;
                int64_t inserted = 0, deleted = 0, updated = 0;
                uint32_t max_conflict = 0;
                swr_v1_memory_table_metadata_fields fields = {
                    &size, &mask, &item_size, &memory_size, &proportion, &created,
                    &rows, &pool, &iterator, &memory,
                    {&count, &inserted, &deleted, &updated, &conflicts, &max_conflict}};
                for (uint32_t legacy = 0; legacy < 2; legacy++) {
                    swr_v1_memory_table_factory factory = {0};
                    factory.rows = requested;
                    factory.conflict = proportions[ratio];
                    factory.legacy = legacy;
                    assert(swr_v1_memory_table_factory_step(NULL, &factory) == 1);
                    uint64_t table_token = 1, mutex_token = 2, vector_token = 3;
                    factory.table = &table_token;
                    assert(swr_v1_memory_table_factory_step(NULL, &factory) == 2);
                    factory.mutex = &mutex_token;
                    if (legacy) {
                        assert(swr_v1_memory_table_factory_step(NULL, &factory) == 3);
                        factory.list = &vector_token;
                    }
                    assert(swr_v1_memory_table_factory_step(&fields, &factory) == 0);
                    assert(size == requested && mask == requested - 1 && !created);
                    assert(proportion == proportions[ratio] && !memory && !rows && !pool && !iterator);
                    assert((factory.index != NULL) == (legacy != 0));
                    if (legacy) {
                        assert(swr_v1_memory_table_columns_count(factory.index) == 0);
                        assert(swr_v1_memory_table_columns_discard(factory.index) == 0);
                    }
                }
                assert(swr_v1_memory_table_metadata_initialize(&fields, requested, proportions[ratio]) == 0);
                item_size = item;
                swr_v1_memory_table_construction state = {0};
                swr_v1_memory_table_construction_effect effect = {0};
                assert(swr_v1_memory_table_construction_step(&fields, &state, &effect) == 1);
                assert(effect.action == 1 && effect.size == state.storage.physical.total);
                state.storage.memory = malloc(effect.size);
                assert(state.storage.memory);
                memset(state.storage.memory, 0x5a, effect.size);
                assert(swr_v1_memory_table_construction_step(&fields, &state, &effect) == 1);
                assert(effect.action == 2 && effect.size == state.storage.physical.pool_size);
                assert(effect.memory == (char *) state.storage.memory + state.storage.physical.pool_offset);
                assert(effect.row_size == 88 + item);
                /* Independent native token witnesses, not actual constructors. */
                uint64_t pool_token = 7, iterator_token = 9;
                state.storage.pool = &pool_token;
                assert(swr_v1_memory_table_construction_step(&fields, &state, &effect) == 1);
                assert(effect.action == 3 && effect.size == 88 + item);
                assert(!created && !memory && !pool && !iterator);
                state.storage.iterator = &iterator_token;
                assert(swr_v1_memory_table_construction_step(&fields, &state, &effect) == 0);
                assert(effect.action == 0 && created && memory == state.storage.memory);
                assert((void *) pool == &pool_token && (void *) iterator == &iterator_token);
                assert(memory_size == state.storage.logical.pool_size);
                for (size_t i = 0; i < size; i++) {
                    assert((char *) rows[i] == (char *) memory + size * sizeof(void *) + (88 + item) * i);
                    const unsigned char *bytes = (const unsigned char *) rows[i];
                    for (size_t j = 0; j < 88; j++) assert(bytes[j] == 0);
                    assert(bytes[88] == 0x5a);
                }
                free(memory);
                cases++;
            }
        }
    }
    printf("{\"passed\":true,\"cases\":%zu,\"factory_cases\":54,\"scope\":\"ordinary C ABI effect model only; Native constructors not executed\"}\n", cases);
    return 0;
}
