// Generation input only: actual selected native effects around the Rust plans.
// All native bodies are inserted into the checksummed pinned-source overlay.

static inline bool table_read_field_value(TableRow *row, const TableV2::Column &col, zval *output, bool array, std::string *name = nullptr) {
    if (col.failed()) return false;
    auto plan = swr_v1_phpcollections_value_plan(array ? 2 : 1, col.kind(), col.valid(), 0, 0, 0);
    long integer = 0;
    double floating = 0;
    char *text = nullptr;
    TableStringLength length = 0;
    auto copy_name = [&]() {
        assert(name != nullptr);
        name->resize(col.name_length());
        return col.copy_name(name->empty() ? nullptr : &(*name)[0], name->size());
    };
    while (plan) {
        const auto action = static_cast<uint8_t>(plan);
        plan >>= 8;
        switch (action) {
        case SWR_VALUE_FALSE: ZVAL_FALSE(output); break;
        case SWR_VALUE_READ_LONG: if (!col.get_value(row, &integer)) return false; break;
        case SWR_VALUE_READ_DOUBLE: if (!col.get_value(row, &floating)) return false; break;
        case SWR_VALUE_READ_STRING: if (!col.get_value(row, &text, &length)) return false; break;
        case SWR_VALUE_RETURN_LONG: ZVAL_LONG(output, integer); break;
        case SWR_VALUE_RETURN_DOUBLE: ZVAL_DOUBLE(output, floating); break;
        case SWR_VALUE_RETURN_STRING: ZVAL_STRINGL(output, text, length); break;
        case SWR_VALUE_ADD_LONG:
            if (!copy_name()) return false;
            add_assoc_long_ex(output, name->data(), name->size(), integer); break;
        case SWR_VALUE_ADD_DOUBLE:
            if (!copy_name()) return false;
            add_assoc_double_ex(output, name->data(), name->size(), floating); break;
        case SWR_VALUE_ADD_STRING:
            if (!copy_name()) return false;
            add_assoc_stringl_ex(output, name->data(), name->size(), text, length); break;
        default: abort();
        }
    }
    return true;
}

static inline bool table_row2array(const TableV2 *table, TableRow *row, zval *return_value) {
    array_init(return_value);
    auto columns = table->columns();
    TableV2::Column col;
    std::string name;
    while (columns.next(col)) {
        if (!table_read_field_value(row, col, return_value, true, &name)) return false;
    }
    return !columns.failed();
}

static inline bool table_get_field_value(TableV2 *table, TableRow *row, zval *return_value, const zend_string *field) {
    const auto col = table->get_column(std::string(ZSTR_VAL(field), ZSTR_LEN(field)));
    return table_read_field_value(row, col, return_value, false);
}

static inline bool table_set_field_value(TableRow *row, const TableV2::Column &col, zval *zv, bool initialize) {
    auto plan = swr_v1_phpcollections_value_plan(3, col.kind(), true, initialize,
                                               zv != nullptr, zv != nullptr && ZVAL_IS_NULL(zv));
    long integer = 0;
    double floating = 0;
    zend_string *text = nullptr;
    bool stored = true;
    while (plan) {
        const auto action = static_cast<uint8_t>(plan);
        plan >>= 8;
        switch (action) {
        case SWR_VALUE_CLEAR: stored = col.clear_value(row); break;
        case SWR_VALUE_CONVERT_LONG: integer = zval_get_long(zv); break;
        case SWR_VALUE_CONVERT_DOUBLE: floating = zval_get_double(zv); break;
        case SWR_VALUE_CONVERT_STRING: text = zval_get_string(zv); break;
        case SWR_VALUE_STORE_LONG: stored = col.set_value(row, &integer, 0); break;
        case SWR_VALUE_STORE_DOUBLE: stored = col.set_value(row, &floating, 0); break;
        case SWR_VALUE_STORE_STRING: stored = col.set_value(row, ZSTR_VAL(text), ZSTR_LEN(text)); break;
        case SWR_VALUE_RELEASE_STRING: zend_string_release(text); break;
        default: abort();
        }
    }
    return stored;
}

static PHP_METHOD(swoole_table, set) {
    TableV2 *table = table_get_and_check_ptr2(ZEND_THIS);
    zval *array;
    char *key;
    size_t keylen;

    ZEND_PARSE_PARAMETERS_START_EX(ZEND_PARSE_PARAMS_THROW, 2, 2)
    Z_PARAM_STRING(key, keylen)
    Z_PARAM_ARRAY(array)
    ZEND_PARSE_PARAMETERS_END_EX(RETURN_FALSE);

    if (!table->ready()) {
        php_swoole_fatal_error(E_ERROR, "the table object does not exist");
        RETURN_FALSE;
    }

    if (swr_v1_phpcollections_key_warning(keylen, SW_TABLE_KEY_SIZE)) {
        php_swoole_fatal_error(E_WARNING, "key[%s] is too long", key);
    }

    int out_flags;
    TableRow *_rowlock = nullptr;
    TableRow *row = table->set(key, keylen, &_rowlock, &out_flags);
    if (!row) {
        _rowlock->unlock();
        php_swoole_error(E_WARNING, "failed to set('%*s'), unable to allocate memory", (int) keylen, key);
        RETURN_FALSE;
    }

    HashTable *ht = Z_ARRVAL_P(array);

    bool columns_ok = true;
    if (out_flags & SW_TABLE_FLAG_NEW_ROW) {
        auto columns = table->columns();
        TableV2::Column col;
        std::string name;
        while (columns.next(col)) {
            name.resize(col.name_length());
            if (!col.copy_name(name.empty() ? nullptr : &name[0], name.size())) {
                columns_ok = false;
                break;
            }
            zval *zv = zend_hash_str_find(ht, name.data(), name.size());
            if (!table_set_field_value(row, col, zv, true)) {
                columns_ok = false;
                break;
            }
        }
        columns_ok = columns_ok && !columns.failed();
    } else {
        const char *k;
        uint32_t klen;
        int ktype;
        zval *zv;
        SW_HASHTABLE_FOREACH_START2(ht, k, klen, ktype, zv) {
            if (k == nullptr) continue;
            const auto col = table->get_column(std::string(k, klen));
            if (col.failed()) { columns_ok = false; break; }
            if (!col.valid()) continue;
            if (!table_set_field_value(row, col, zv, false)) { columns_ok = false; break; }
        }
        (void) ktype;
        SW_HASHTABLE_FOREACH_END();
    }
    _rowlock->unlock();
    if (!columns_ok) {
        zend_throw_error(nullptr, "Swoole Table column collection cursor is invalid");
        RETURN_FALSE;
    }
    RETURN_TRUE;
}

static void table_update(INTERNAL_FUNCTION_PARAMETERS, bool subtract) {
    TableV2 *table = table_get_and_check_ptr2(ZEND_THIS);
    char *key;
    size_t key_len;
    char *col;
    size_t col_len;
    zval *changeby = nullptr;

    if (zend_parse_parameters(ZEND_NUM_ARGS(), "ss|z", &key, &key_len, &col, &col_len, &changeby) == FAILURE) {
        RETURN_FALSE;
    }

    int out_flags;
    TableRow *_rowlock = nullptr;
    TableRow *row = table->set(key, key_len, &_rowlock, &out_flags);
    if (!row) {
        _rowlock->unlock();
        php_swoole_fatal_error(E_WARNING, "unable to allocate memory");
        RETURN_FALSE;
    }

    const auto column = table->get_column(std::string(col, col_len));
    if (column.failed()) {
        _rowlock->unlock();
        zend_throw_error(nullptr, "Swoole Table column collection cursor is invalid");
        RETURN_FALSE;
    }
    if (!column.valid()) {
        _rowlock->unlock();
        php_swoole_fatal_error(E_WARNING, "column[%s] does not exist", col);
        RETURN_FALSE;
    }

    if (out_flags & SW_TABLE_FLAG_NEW_ROW) {
        table->clear_row(row);
    }

    const auto kind = swr_v1_phpcollections_kind(column.kind());
    if (kind == TableColumn::TYPE_STRING) {
        _rowlock->unlock();
        php_swoole_fatal_error(E_WARNING, subtract ? "can't execute 'decr' on a string type column" : "can't execute 'incr' on a string type column");
        RETURN_FALSE;
    } else if (kind == TableColumn::TYPE_FLOAT) {
        double set_value = 0;
        memcpy(&set_value, row->data + column.index(), sizeof(set_value));
        const double amount = changeby ? zval_get_double(changeby) : 1;
        set_value = swr_v1_phpcollections_float_update(set_value, amount, subtract);
        if (!column.set_value(row, &set_value, 0)) {
            _rowlock->unlock();
            zend_throw_error(nullptr, "Swoole Table column collection cursor is invalid");
            RETURN_FALSE;
        }
        RETVAL_DOUBLE(set_value);
    } else {
        long set_value = 0;
        memcpy(&set_value, row->data + column.index(), sizeof(set_value));
        const long amount = changeby ? zval_get_long(changeby) : 1;
        if (!swr_v1_phpcollections_integer_update(set_value, amount, subtract, &set_value)) {
            // Preserve the original native undefined overflow domain; no parity claim.
            if (subtract) { set_value -= amount; } else { set_value += amount; }
        }
        if (!column.set_value(row, &set_value, 0)) {
            _rowlock->unlock();
            zend_throw_error(nullptr, "Swoole Table column collection cursor is invalid");
            RETURN_FALSE;
        }
        RETVAL_LONG(set_value);
    }
    _rowlock->unlock();
}

static PHP_METHOD(swoole_table, get) {
    TableV2 *table = table_get_and_check_ptr2(ZEND_THIS);
    char *key;
    size_t keylen;
    zend_string *field = nullptr;

    ZEND_PARSE_PARAMETERS_START_EX(ZEND_PARSE_PARAMS_THROW, 1, 2)
    Z_PARAM_STRING(key, keylen)
    Z_PARAM_OPTIONAL
    Z_PARAM_STR_OR_NULL(field)
    ZEND_PARSE_PARAMETERS_END_EX(RETURN_FALSE);

    TableRow *_rowlock = nullptr;
    TableRow *row = table->get(key, keylen, &_rowlock);
    bool columns_ok = true;
    const auto action = swr_v1_phpcollections_get_action(row != nullptr, field != nullptr);
    if (action == 0) {
        RETVAL_FALSE;
    } else if (action == 1) {
        columns_ok = table_get_field_value(table, row, return_value, field);
    } else {
        columns_ok = table_row2array(table, row, return_value);
    }
    _rowlock->unlock();
    if (!columns_ok) {
        zval_ptr_dtor(return_value);
        ZVAL_FALSE(return_value);
        zend_throw_error(nullptr, "Swoole Table column collection cursor is invalid");
    }
}

static PHP_METHOD(swoole_table, count) {
#define COUNT_NORMAL 0
#define COUNT_RECURSIVE 1
    TableV2 *table = table_get_ptr(ZEND_THIS);
    if (!table) {
        RETURN_LONG(0);
    }

    zend_long mode = COUNT_NORMAL;
    if (zend_parse_parameters(ZEND_NUM_ARGS(), "|l", &mode) == FAILURE) {
        RETURN_FALSE;
    }

    size_t column_count = 0;
    if (mode != COUNT_NORMAL) {
        const auto columns = table->columns();
        if (columns.failed()) {
            zend_throw_error(nullptr, "Swoole Table column collection cursor is invalid");
            RETURN_FALSE;
        }
        column_count = columns.count();
    }
    RETURN_LONG(swr_v1_phpcollections_count(mode, table->count(), column_count));
}

static PHP_METHOD(swoole_table, current) {
    TableV2 *table = table_get_and_check_ptr2(ZEND_THIS);
    auto row = table->current();
    if (row->key_len == 0) {
        RETURN_NULL();
    }
    if (!table_row2array(table, row, return_value)) {
        zval_ptr_dtor(return_value);
        ZVAL_FALSE(return_value);
        zend_throw_error(nullptr, "Swoole Table column collection cursor is invalid");
    }
}
