/* Utilities-only shared FFI archive linkage and normal owned-state custody. */
#include <assert.h>
#include <string.h>
#include "swoole_rs_utilities.h"
extern uint32_t swr_v1_abi_version(void);
extern uint64_t swr_v1_feature_bits(void);
int main(void) {
    assert(swr_v1_abi_version() == 1);
    assert(swr_v1_feature_bits() == 512);
    struct SwrUtilsLogState *state = NULL;
    assert(swr_v1_utils_log_state_create(1024, &state) == SWR_UTILS_STATE_OK);
    assert(swr_v1_utils_log_state_scalar_get(state, SWR_UTILS_STATE_LEVEL) == 2);
    const uint8_t path[] = "ffi-owned-path";
    assert(swr_v1_utils_log_state_text_set(state, SWR_UTILS_STATE_FILE, path, sizeof(path)-1) == SWR_UTILS_STATE_OK);
    assert(swr_v1_utils_log_state_text_copy(state, SWR_UTILS_STATE_FILE, SWR_UTILS_STATE_REAL_FILE) == SWR_UTILS_STATE_OK);
    assert(strcmp(swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_REAL_FILE), (const char *) path) == 0);
    assert(swr_v1_utils_log_state_scalar_set(state, SWR_UTILS_STATE_BACKTRACE, 1) == SWR_UTILS_STATE_OK);
    swr_v1_utils_log_state_reset(state);
    assert(swr_v1_utils_log_state_scalar_get(state, SWR_UTILS_STATE_BACKTRACE) == 1);
    uint32_t phase = 0;
    assert(swr_v1_utils_log_state_file_step(state, &phase, 1, -1) == SWR_UTILS_LOG_FILE_DONE);
    phase = 0;
    assert(swr_v1_utils_log_state_redirect_step(state, &phase, 1, 0) == SWR_UTILS_REDIRECT_NO_FILE);
    phase = 0;
    assert(swr_v1_utils_log_state_config_step(state, &phase, 2, 0) == SWR_UTILS_LOG_CONFIG_ASSIGN_STREAM);
    phase = 0;
    assert(swr_v1_utils_log_state_emit_step(state, &phase, 2, 0, 0, 123) == SWR_UTILS_LOG_PUT_DATE);
    swr_v1_utils_log_state_clear(state, 0);
    assert(strcmp(swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_FILE), "") == 0);
    assert(strcmp(swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_REAL_FILE), (const char *)path) == 0);
    swr_v1_utils_log_state_destroy(state);
    return 0;
}
