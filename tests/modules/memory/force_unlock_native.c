/* Test-only PHP observer. No Swoole/Rust library or original PHPT is modified. */
#include <php.h>
#include <execinfo.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#if !defined(__linux__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__ || UINTPTR_MAX != UINT64_MAX || defined(ZTS)
#error "This diagnostic requires Linux little-endian 64-bit PHP NTS"
#endif

static uintptr_t watched;
static zif_handler original_get;
static zend_function *wrapped_get;
static void (*original_error)(int, zend_string *, const uint32_t, zend_string *);

static int oom_state(void) {
#ifdef ZEND_HAS_OOM
    return EG(delayed_oom).state;
#else
    return -1;
#endif
}

static void observe(const char *phase) {
    unsigned lock = 999, owner = 0;
    if (watched) {
        lock = __atomic_load_n((unsigned *) watched, __ATOMIC_RELAXED);
        memcpy(&owner, (void *) (watched + 4), 4);
    }
    char line[256];
    int n = snprintf(line, sizeof(line), "M12_NATIVE phase=%s pid=%d lock=%u owner=%u oom=%d\n",
                     phase, getpid(), lock, owner, oom_state());
    if (n > 0 && n < (int) sizeof(line)) {
        (void) write(STDERR_FILENO, line, n);
    }
}

static void diagnostic_get(INTERNAL_FUNCTION_PARAMETERS) {
    observe("get-enter");
    original_get(INTERNAL_FUNCTION_PARAM_PASSTHRU);
    observe("get-return");
    zval *text = Z_TYPE_P(return_value) == IS_ARRAY
        ? zend_hash_str_find(Z_ARR_P(return_value), "string", 6) : NULL;
    char line[128];
    int n = snprintf(line, sizeof(line), "M12_NATIVE return-type=%d string-bytes=%zu\n",
                     Z_TYPE_P(return_value), text && Z_TYPE_P(text) == IS_STRING ? Z_STRLEN_P(text) : 0);
    if (n > 0 && n < (int) sizeof(line)) {
        (void) write(STDERR_FILENO, line, n);
    }
}

static void diagnostic_error(int type, zend_string *file, const uint32_t lineno, zend_string *message) {
    if (type == E_ERROR) {
        observe("fatal-before");
        void *frames[32];
        int n = backtrace(frames, 32);
        backtrace_symbols_fd(frames, n, STDERR_FILENO);
    }
    original_error(type, file, lineno, message);
    if (type == E_ERROR) {
        observe("fatal-after");
    }
}

PHP_FUNCTION(swr_memory_diag_watch_table) {
    ZEND_PARSE_PARAMETERS_NONE();
    watched = 0;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps) {
        RETURN_FALSE;
    }
    char line[512], permissions[5];
    unsigned long start, end;
    while (fgets(line, sizeof(line), maps)) {
        if (sscanf(line, "%lx-%lx %4s", &start, &end, permissions) != 3
            || strcmp(permissions, "rw-s") || end - start < 100UL * 1024 * 1024) {
            continue;
        }
        /* Pinned mmap: 8-byte mapping header, 64 root pointers, 88-byte rows. */
        uint64_t pointers[64];
        memcpy(pointers, (void *) (start + 8), sizeof(pointers));
        for (unsigned i = 0; i < 64; i++) {
            uintptr_t p = pointers[i];
            unsigned char header[88];
            if (p < start || p > end - sizeof(header)) {
                continue;
            }
            memcpy(header, (void *) p, sizeof(header));
            if (header[9] == 4 && memcmp(header + 24, "test", 4) == 0) {
                watched = p;
            }
        }
    }
    fclose(maps);
    observe("watch-installed");
    RETURN_BOOL(watched != 0);
}

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_watch, 0, 0, _IS_BOOL, 0)
ZEND_END_ARG_INFO()
static const zend_function_entry functions[] = {
    PHP_FE(swr_memory_diag_watch_table, arginfo_watch)
    PHP_FE_END
};

PHP_MINIT_FUNCTION(swr_memory_diagnostic) {
    (void) type;
    (void) module_number;
    zend_class_entry *ce = zend_hash_str_find_ptr(CG(class_table), "swoole\\table", sizeof("swoole\\table") - 1);
    if (!ce) {
        return FAILURE;
    }
    wrapped_get = zend_hash_str_find_ptr(&ce->function_table, "get", 3);
    if (!wrapped_get || wrapped_get->type != ZEND_INTERNAL_FUNCTION) {
        return FAILURE;
    }
    original_get = wrapped_get->internal_function.handler;
    wrapped_get->internal_function.handler = diagnostic_get;
    original_error = zend_error_cb;
    zend_error_cb = diagnostic_error;
    return SUCCESS;
}

PHP_MSHUTDOWN_FUNCTION(swr_memory_diagnostic) {
    (void) type;
    (void) module_number;
    if (wrapped_get->internal_function.handler == diagnostic_get) {
        wrapped_get->internal_function.handler = original_get;
    }
    if (zend_error_cb == diagnostic_error) {
        zend_error_cb = original_error;
    }
    return SUCCESS;
}

zend_module_entry swr_memory_diagnostic_module_entry = {
    STANDARD_MODULE_HEADER, "swr_memory_diagnostic", functions,
    PHP_MINIT(swr_memory_diagnostic), PHP_MSHUTDOWN(swr_memory_diagnostic),
    NULL, NULL, NULL, "0.0.0", STANDARD_MODULE_PROPERTIES
};
ZEND_GET_MODULE(swr_memory_diagnostic)
