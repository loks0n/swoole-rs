/* Actual C11 consumer of the scoped-owner ABI; bounded normal values only. */
#include "swoole_rs_utilities.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    struct SwrUtilsLogState *state = NULL;
    struct SwrUtilsLogPath *path = NULL;
    assert(swr_v1_utils_log_state_create(1024, &state) == SWR_UTILS_STATE_OK);
    char file[] = "first", date[] = "20400102";
    assert(swr_v1_utils_log_path_create(state, 1, (const uint8_t *) file, 5, &path) == SWR_UTILS_STATE_OK);
    memset(file, 'x', 5); /* Native effect interval cannot change captured bytes. */
    assert(swr_v1_utils_log_path_rotate(path, (const uint8_t *) date, 8) == SWR_UTILS_STATE_OK);
    memset(date, '0', 8);
    size_t length = 0;
    const char *value = swr_v1_utils_log_path_get(path, &length);
    assert(length == 14 && memcmp(value, "first.20400102", 14) == 0 && value[length] == 0);
    assert(swr_v1_utils_log_state_text_set(state, SWR_UTILS_STATE_REAL_FILE,
        (const uint8_t *) value, length) == SWR_UTILS_STATE_OK);
    uint32_t phase = SWR_UTILS_LOG_EMIT_PATH_PHASE;
    assert(swr_v1_utils_log_path_emit_step(state, &phase, 3, path, 0, 123) == SWR_UTILS_LOG_PUT_SKIP);
    assert(phase == SWR_UTILS_LOG_PUT_MICROS_PHASE);
    assert(swr_v1_utils_log_state_text_set(state, SWR_UTILS_STATE_REAL_FILE,
        (const uint8_t *) "changed", 7) == SWR_UTILS_STATE_OK);
    phase = SWR_UTILS_LOG_EMIT_PATH_PHASE;
    assert(swr_v1_utils_log_path_emit_step(state, &phase, 3, path, 0, 123) == SWR_UTILS_LOG_EMIT_ROTATION_LOCK);
    assert(swr_v1_utils_log_path_adopt(state, path) == SWR_UTILS_STATE_OK);
    assert(swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_REAL_FILE) == value);
    assert(swr_v1_utils_log_state_text_set(state, SWR_UTILS_STATE_FILE,
        (const uint8_t *) "before\0hidden", 13) == SWR_UTILS_STATE_OK);
    path = NULL;
    assert(swr_v1_utils_log_path_create(state, 0, NULL, 0, &path) == SWR_UTILS_STATE_OK);
    swr_v1_utils_log_state_clear(state, 0);
    assert(strcmp(swr_v1_utils_log_path_get(path, &length), "before") == 0 && length == 6);
    swr_v1_utils_log_path_destroy(path);
    swr_v1_utils_log_state_destroy(state);
    puts("{\"c_path_checks\":8,\"scoped_exports\":6}");
    return 0;
}
