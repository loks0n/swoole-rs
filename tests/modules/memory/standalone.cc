// Standalone native-runtime witnesses: no PHP loader or Zend frame is involved.
#include "swoole_table.h"
#include <cassert>
#include <atomic>
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <new>

extern "C" int swr_memory_probe();
extern "C" int swr_memory_mapping_probe();
#ifdef SWOOLE_RS_MEMORY
extern "C" int swr_memory_odd_table_probe();
#endif

// Fault only native C++ owner/vector allocations, independently of Rust's
// unchanged fallible-allocator tests. Never fail sanitizer/runtime allocations.
static thread_local int fail_after = -1;
static std::atomic<long> live_cpp_allocations{0};
void *operator new(std::size_t size) {
    if (fail_after >= 0 && fail_after-- == 0) throw std::bad_alloc();
    if (void *result = std::malloc(size ? size : 1)) {
        live_cpp_allocations.fetch_add(1, std::memory_order_relaxed);
        return result;
    }
    throw std::bad_alloc();
}
void operator delete(void *data) noexcept {
    if (data) live_cpp_allocations.fetch_sub(1, std::memory_order_relaxed);
    std::free(data);
}
void operator delete(void *data, std::size_t) noexcept { ::operator delete(data); }

#ifdef SWOOLE_RS_MEMORY
static int clearing() {
    using swoole::Table;
    using swoole::TableColumn;
    for (unsigned count : {0, 1, 7, 8, 9, 15, 16, 17, 33}) {
        auto *table = Table::make(64, 0.2); assert(table);
        for (unsigned i = 0; i < count; ++i) {
            const auto kind = static_cast<TableColumn::Type>(1 + i % 3);
            assert(table->add_column("field" + std::to_string(i), kind, 4));
        }
        assert(table->create());
        swoole::TableRow *lock = nullptr;
        auto *row = table->set("row", 3, &lock, nullptr); assert(row);
        unsigned char header[sizeof(*row)];
        memcpy(header, row, sizeof(header));
        const auto verify = [&]() {
            std::vector<unsigned char> expected(count * 8, 0xa5);
            memset(row->data, 0xa5, expected.size());
            for (const auto *column : *table->column_list) {
                memset(expected.data() + column->index, 0, column->type == TableColumn::TYPE_STRING ? 4 : 8);
            }
            table->clear_row(row);
            assert(memcmp(header, row, sizeof(header)) == 0);
            if (!expected.empty()) assert(memcmp(row->data, expected.data(), expected.size()) == 0);
        };
        verify();
        if (count >= 5) {
            // Public descriptors remain live, not an immutable cached schema.
            auto *moved = table->column_list->at(3);
            auto *changed = table->column_list->at(4);
            moved->index = 1;
            changed->type = TableColumn::TYPE_STRING;
            std::reverse(table->column_list->begin(), table->column_list->end());
            verify();
            moved->index = 24;
            changed->type = TableColumn::TYPE_FLOAT;
        }
        lock->unlock(); table->destroy();
    }
    printf("{\"passed\":true,\"clear_schemas\":9,\"live_descriptor_mutations\":7,\"maximum_columns\":33}\n");
    return 0;
}

static int creation() {
    using swoole::Table;
    using swoole::TableColumn;
    for (int allocation : {0, 1, 2}) {
        auto *table = Table::make(64, 0.2); assert(table);
        assert(table->add_column("field", TableColumn::TYPE_INT, 0));
        const auto before = live_cpp_allocations.load(std::memory_order_relaxed);
        bool threw = false;
        fail_after = allocation;
        try { table->create(); }
        catch (const std::bad_alloc &) { threw = true; }
        fail_after = -1;
        assert(threw);
        assert(!table->ready() && !table->is_created());
        assert(table->get_memory_size() == 0);
        assert(live_cpp_allocations.load(std::memory_order_relaxed) == before);
        assert(table->create()); // The same owner remains usable after rollback.
        swoole::TableRow *lock = nullptr;
        auto *row = table->set("row", 3, &lock, nullptr); assert(row);
        long value = 42, read = 0;
        row->set_value(table->get_column("field"), &value, 0);
        lock->unlock();
        row = table->get("row", 3, &lock); assert(row);
        row->get_value(table->get_column("field"), &read);
        assert(read == value);
        lock->unlock();
        table->destroy();
    }
    printf("{\"passed\":true,\"create_oom\":3,\"same_owner_retries\":3}\n");
    return 0;
}

static int metadata() {
    using swoole::Table;
    using swoole::TableColumn;
    for (uint32_t count : {0x90000000u, 1024u}) {
        auto *table = Table::make(count, 0.2); assert(table);
        table->destroy(); // Also valid before create(), unlike leaking a raw owner.
    }
    for (int allocation : {0, 1}) {
        bool threw = false;
        fail_after = allocation;
        try {
            auto *table = Table::make(64, 0.2);
            fail_after = -1;
            if (table) table->destroy();
        } catch (const std::bad_alloc &) {
            fail_after = -1;
            threw = true;
        }
        assert(threw);
    }
    auto *table = Table::make(64, 0.2); assert(table);
    const auto original_size = table->calc_memory_size();
    for (int allocation : {0, 1}) {
        bool threw = false;
        fail_after = allocation;
        try { table->add_column("field", TableColumn::TYPE_INT, 0); }
        catch (const std::bad_alloc &) { threw = true; }
        fail_after = -1;
        assert(threw && table->column_list->empty());
        assert(table->get_column("field") == nullptr);
        assert(table->calc_memory_size() == original_size);
    }
    assert(table->add_column("field", TableColumn::TYPE_INT, 0));
    assert(table->column_list->size() == 1);
    table->destroy();
    for (unsigned i = 0; i < 64; ++i) {
        table = Table::make(64, 0.2); assert(table);
        assert(table->add_column("same", TableColumn::TYPE_INT, 0));
        auto *first = table->get_column("same"); assert(first);
        // Native atomic row locks require aligned complete rows. Packed odd
        // field widths are separately exercised in the Rust instruction gate.
        assert(table->add_column("same", TableColumn::TYPE_STRING, 12));
        assert(table->get_column("same") == first && table->column_list->size() == 2);
        auto *second = table->column_list->back();
        assert(second != first && second->index == first->size);
        assert(table->create());
        swoole::TableRow *lock = nullptr;
        auto *row = table->set("row", 3, &lock, nullptr); assert(row);
        table->clear_row(row);
        long value = 17, read = 0;
        row->set_value(first, &value, 0); row->get_value(first, &read);
        assert(read == value);
        char *string = nullptr; uint32_t length = 1;
        row->get_value(second, &string, &length); assert(length == 0);
        lock->unlock(); table->destroy();
    }
    printf("{\"passed\":true,\"uncreated_destroy\":2,\"make_oom\":2,\"column_oom\":2,\"duplicate_destroy\":64}\n");
    return 0;
}
#endif

int main(int argc, char **argv) {
    if (argc > 2) return 2;
    swoole_init();
    int result = 2;
    if (argc == 1) result = swr_memory_probe();
#ifdef SWOOLE_RS_MEMORY
    else if (strcmp(argv[1], "mapping") == 0) result = swr_memory_mapping_probe();
    else if (strcmp(argv[1], "clearing") == 0) result = clearing();
    else if (strcmp(argv[1], "creation") == 0) result = creation();
    else if (strcmp(argv[1], "metadata") == 0) result = metadata();
    else if (strcmp(argv[1], "odd-rows") == 0) result = swr_memory_odd_table_probe();
#endif
    swoole_clean();
    return result;
}
