#pragma once
#include "swoole_table.h"
#include <memory>

namespace swoole {
// A new typed surface, never a cast/subclass of the deleted-constructor Table.
// The legacy row/storage core is obtained solely through its existing factory.
class TableV2 final {
    Table *core_;
    swr_v1_memory_records *columns_ = nullptr;

    explicit TableV2(Table *core)
        : core_(core), conflict_count(core->conflict_count), insert_count(core->insert_count),
          delete_count(core->delete_count), update_count(core->update_count), conflict_max_level(core->conflict_max_level) {}

    ~TableV2() {
        const int status = swr_v1_memory_records_close(&columns_);
        assert(status == 0);
        (void) status;
        // This core was constructed without legacy column containers.
        core_->destroy_impl(false);
    }

  public:
    size_t &conflict_count;
    sw_atomic_long_t &insert_count, &delete_count, &update_count;
    uint32_t &conflict_max_level;

    TableV2(const TableV2 &) = delete;
    TableV2 &operator=(const TableV2 &) = delete;

    class ColumnCursor;
    class Column {
        friend class TableV2;
        friend class ColumnCursor;
        const swr_v1_memory_records *owner_ = nullptr;
        swr_v1_memory_record_view view_{};
        mutable int status_ = 0;
      public:
        Column() = default;
        bool valid() const { return status_ == 1; }
        bool failed() const { return status_ < 0; }
        uint32_t kind() const { return view_.kind; }
        uint32_t width() const { return view_.width; }
        size_t index() const { return view_.index; }
        size_t name_length() const { return view_.name_length; }
        bool copy_name(char *buffer, size_t capacity) const {
            if (!valid()) return false;
            if (swr_v1_memory_records_copy_name(owner_, &view_, reinterpret_cast<uint8_t *>(buffer), capacity) != 0) {
                status_ = -1;
                return false;
            }
            return true;
        }
        // Typed row access using copied scalar facts, no reconstructed native
        // TableColumn object or Rust name span. Caller owns the row lock.
        bool clear_value(TableRow *row) const {
            return valid() && swr_v1_memory_table_clear_value(
                reinterpret_cast<swr_v1_memory_table_row *>(row), index(), width(), kind()) == 0;
        }
        bool get_value(const TableRow *row, long *value) const {
            return valid() && kind() == TableColumn::TYPE_INT && swr_v1_memory_table_get_number(
                reinterpret_cast<const swr_v1_memory_table_row *>(row), index(), value) == 0;
        }
        bool get_value(const TableRow *row, double *value) const {
            return valid() && kind() == TableColumn::TYPE_FLOAT && swr_v1_memory_table_get_number(
                reinterpret_cast<const swr_v1_memory_table_row *>(row), index(), value) == 0;
        }
        bool get_value(TableRow *row, char **value, TableStringLength *length) const {
            return valid() && kind() == TableColumn::TYPE_STRING && swr_v1_memory_table_get_string(
                reinterpret_cast<swr_v1_memory_table_row *>(row), index(), width(),
                reinterpret_cast<uint8_t **>(value), length) == 0;
        }
        bool set_value(TableRow *row, const void *value, size_t length) const {
            if (!valid()) return false;
            swr_v1_memory_table_value state{};
            state.row = reinterpret_cast<swr_v1_memory_table_row *>(row);
            state.value = value;
            state.length = length;
            state.index = index();
            state.width = width();
            state.kind = kind();
            int status = swr_v1_memory_table_value_step(&state);
            if (status == 1) {
                std::string name(name_length(), '\0');
                if (!copy_name(name.empty() ? nullptr : &name[0], name.size())) return false;
                // Preserve the original public warning attribution despite the
                // new descriptor scope; logging remains an effect after Rust.
                if (SW_LOG_WARNING >= swoole_get_log_level()) {
                    const size_t length = sw_snprintf(sw_error, SW_ERROR_MSG_SIZE,
                        "TableRow::set_value(): [key=%s,field=%s]string value is too long", row->key, name.c_str());
                    sw_logger()->put(SW_LOG_WARNING, sw_error, length);
                }
                status = swr_v1_memory_table_value_step(&state);
            }
            return status == 0;
        }

    };

    class ColumnCursor {
        const swr_v1_memory_records *owner_;
        swr_v1_memory_record_cursor state_{};
        int status_;
      public:
        explicit ColumnCursor(const swr_v1_memory_records *owner)
            : owner_(owner), status_(swr_v1_memory_records_cursor_open(owner, &state_)) {}
        size_t count() const { return state_.count; }
        size_t unique_count() const { return state_.unique_count; }
        bool failed() const { return status_ < 0; }
        bool next(Column &column) {
            column = Column{};
            if (failed()) return false;
            column.owner_ = owner_;
            status_ = swr_v1_memory_records_cursor_next(owner_, &state_, &column.view_);
            column.status_ = status_;
            return status_ == 1;
        }
    };

    static TableV2 *make(uint32_t rows, float conflict) {
        auto release_core = [](Table *core) { core->destroy_impl(false); };
        std::unique_ptr<Table, decltype(release_core)> core(Table::make_impl(rows, conflict, false), release_core);
        if (!core) return nullptr;
        assert(core->column_map == nullptr && core->column_list == nullptr);
        auto release_table = [](TableV2 *table) { delete table; };
        std::unique_ptr<TableV2, decltype(release_table)> table(new TableV2(core.get()), release_table);
        (void) core.release();
        if (swr_v1_memory_records_open(&table->columns_) != 0) return nullptr;
        return table.release();
    }

    bool add_column(const std::string &name, TableColumn::Type kind, size_t requested) {
        const int status = swr_v1_memory_records_declare(columns_, &core_->item_size,
            reinterpret_cast<const uint8_t *>(&core_->created),
            reinterpret_cast<const uint8_t *>(name.data()), name.size(), static_cast<uint32_t>(kind), requested);
        if (status == -2) swoole_warning("unknown column type");
        return status == 0;
    }
    Column get_column(const std::string &name) const {
        Column column;
        column.owner_ = columns_;
        column.status_ = swr_v1_memory_records_get(columns_,
            reinterpret_cast<const uint8_t *>(name.data()), name.size(), &column.view_);
        return column;
    }
    ColumnCursor columns() const { return ColumnCursor(columns_); }
    size_t get_column_size() const {
        const auto cursor = columns();
        assert(!cursor.failed());
        return cursor.unique_count();
    }
    void clear_row(TableRow *row) const {
        const int status = swr_v1_memory_records_clear(columns_, reinterpret_cast<swr_v1_memory_table_row *>(row));
        assert(status == 0);
        (void) status;
    }
    // Swoole\Table's column records (crates/phpcollections), and the core's
    // item_size and created flag their declarations update and check.
    swr_v1_memory_records *records(size_t **item_size, const uint8_t **created) {
        *item_size = &core_->item_size;
        *created = reinterpret_cast<const uint8_t *>(&core_->created);
        return columns_;
    }
    void destroy() { delete this; }

    bool create() { return core_->create(); }
    bool is_created() const { return core_->is_created(); }
    bool ready() const { return core_->ready(); }
    void set_hash_func(HashFunc callback) { core_->set_hash_func(callback); }
    size_t count() const { return core_->count(); }
    TableRow *set(const char *key, uint16_t length, TableRow **lock, int *flags) { return core_->set(key, length, lock, flags); }
    TableRow *get(const char *key, uint16_t length, TableRow **lock) const { return core_->get(key, length, lock); }
    bool del(const char *key, uint16_t length) { return core_->del(key, length); }
    bool exists(const char *key, uint16_t length) const { return core_->exists(key, length); }
    bool exists(const std::string &key) const { return core_->exists(key); }
    void forward() const { core_->forward(); }
    void rewind() const { core_->rewind(); }
    TableRow *current() const { return core_->current(); }
    size_t calc_memory_size() const { return core_->calc_memory_size(); }
    size_t get_memory_size() const { return core_->get_memory_size(); }
    size_t get_size() const { return core_->get_size(); }
    float get_conflict_proportion() const { return core_->get_conflict_proportion(); }
    uint32_t get_available_slice_num() const { return core_->get_available_slice_num(); }
    uint32_t get_total_slice_num() const { return core_->get_total_slice_num(); }
};
}  // namespace swoole
