// ABI2 fixture storage is solely the real Rust context. FILE/mutex publication
// remains native; the reference fixture above retains its original fields.
struct StateThreadFixture {
    SwrUtilsLogState *state = nullptr;
    struct OpenedValue {
        SwrUtilsLogState *state;
        OpenedValue &operator=(bool value) {
            assert(mutex_held);
            assert(swr_v1_utils_log_state_scalar_set(state, SWR_UTILS_STATE_OPENED, value) == SWR_UTILS_STATE_OK);
            return *this;
        }
    };
    struct { OpenedValue value; } opened;
    FILE *log_fp = nullptr;
    TrackedMutex lock;
    StateThreadFixture() : opened{{nullptr}} {
        assert(swr_v1_utils_log_state_create(std::string().max_size(), &state) == SWR_UTILS_STATE_OK);
        opened.value.state = state;
        assert(swr_v1_utils_log_state_scalar_set(state, SWR_UTILS_STATE_OPENED, 1) == SWR_UTILS_STATE_OK);
        assert(swr_v1_utils_log_state_scalar_set(state, SWR_UTILS_STATE_LEVEL, 0) == SWR_UTILS_STATE_OK);
        const char format[] = "M14";
        assert(swr_v1_utils_log_state_text_set(state, SWR_UTILS_STATE_DATE,
            reinterpret_cast<const uint8_t *>(format), sizeof(format) - 1) == SWR_UTILS_STATE_OK);
    }
    ~StateThreadFixture() { swr_v1_utils_log_state_destroy(state); }
    const char *get_file() const { return swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_FILE); }
    const char *get_real_file() const { return swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_REAL_FILE); }
    std::string gen_real_file(const std::string &) { std::abort(); }
    SwrUtilsLogPath *make_real_path(const char *, size_t) const { std::abort(); }
    void reopen_without_lock() { std::abort(); }
};
// Observe the native observation boundary; the fields themselves stay in Rust.
inline uint32_t observed_state_emit_step(const SwrUtilsLogState *state, uint32_t *phase,
                                         int32_t level, uint8_t changed, uint8_t acquired, int32_t pid) {
    if (*phase == SWR_UTILS_LOG_PUT_FILE_LOCK_PHASE || *phase == SWR_UTILS_LOG_PUT_FILE_UNLOCK_PHASE) {
        assert(mutex_held && "owned opened read before Logger mutex");
        ++opened_reads;
    }
    return swr_v1_utils_log_state_emit_step(state, phase, level, changed, acquired, pid);
}
#define swr_v1_utils_log_state_emit_step observed_state_emit_step

inline uint32_t observed_path_emit_step(const SwrUtilsLogState *state, uint32_t *phase,
                                        int32_t level, const SwrUtilsLogPath *path, uint8_t acquired, int32_t pid) {
    if (*phase == SWR_UTILS_LOG_PUT_FILE_LOCK_PHASE || *phase == SWR_UTILS_LOG_PUT_FILE_UNLOCK_PHASE) {
        assert(mutex_held && "owned opened read before Logger mutex");
        ++opened_reads;
    }
    return swr_v1_utils_log_path_emit_step(state, phase, level, path, acquired, pid);
}
#define swr_v1_utils_log_path_emit_step observed_path_emit_step
