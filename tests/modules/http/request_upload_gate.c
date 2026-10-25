/* Ordinary Rust metadata operations only: no parser, file or Native resource. */
#include "swoole_rs_http_request_v2.h"
#include <stdio.h>
#include <string.h>
#define CHECK(expression) do { if (!(expression)) return 1; } while (0)
int main(void) {
    swr_v2_http_request *owner = swr_v2_http_request_new();
    CHECK(owner != NULL);
    CHECK(swr_v2_http_request_control(owner, SWR_HTTP_REQUEST_V2_ADMIT_FORM, 0, 0) == 0);
    CHECK(swr_v2_http_request_text_set(owner, 1, (const uint8_t *) "Content-Disposition", 19) == 0);
    CHECK(swr_v2_http_request_text_set(owner, 0, (const uint8_t *) "/ordinary", 9) == 0);
    size_t count = 0;
    const uint32_t *plan = swr_v2_http_request_upload_plan(owner, 0, 0, &count);
    CHECK(plan != NULL && count == 1 && plan[0] == 1);
    uint8_t output[128]; memset(output, 0xcc, sizeof(output));
    CHECK(swr_v2_http_request_upload_template(owner, output, sizeof(output)) == 0);
    const char expected[] = "/ordinary/swoole.upfile.XXXXXX";
    CHECK(memcmp(output, expected, sizeof(expected)) == 0);
    CHECK(output[sizeof(expected)] == 0xcc);
    uint8_t scratch[64]; memset(scratch, 0xcc, sizeof(scratch));
    swr_v1_http_proxy_text text = {NULL, 0};
    swr_v2_http_request_text_snapshot *lease = NULL;
    CHECK(swr_v2_http_request_text_snapshot_new(owner, 1, scratch, sizeof(scratch), &text, &lease) == 0);
    CHECK(lease == NULL && text.data == scratch && text.length == 19);
    CHECK(memcmp(text.data, "Content-Disposition", 20) == 0);
    swr_v2_http_request_text_snapshot_drop(lease);
    uint8_t large[80]; memset(large, 'n', sizeof(large));
    CHECK(swr_v2_http_request_text_set(owner, 1, large, sizeof(large)) == 0);
    CHECK(swr_v2_http_request_text_snapshot_new(owner, 1, scratch, sizeof(scratch), &text, &lease) == 0);
    CHECK(lease != NULL && text.length == sizeof(large));
    CHECK(memcmp(text.data, large, sizeof(large)) == 0 && text.data[text.length] == 0);
    swr_v2_http_request_text_snapshot_drop(lease);
    swr_v2_http_request_drop(owner);
    puts("{\"ordinary_upload_metadata\":true,\"parser_io_executed\":false}");
    return 0;
}
