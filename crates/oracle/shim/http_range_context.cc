// The candidate StaticHandler::parse_range: build.rs copies it, with ensure_boundary and
// resume_range_header, from static_handler.cc with the http static-ranges patch applied
// (calling the Rust static context) into http_range_candidate.inc unchanged. The facade
// gives them the handler's context, and the file size, MIME type, boundary and If-Range
// verdict chosen by the caller; the result is read back from the context.
#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/types.h>
#include "swoole_rs_http_context.h"

// As upstream include/swoole_config.h.
#define SW_HTTP_SERVER_PART_HEADER 256
#define SW_HTTP_SERVER_BOUNDARY_TOTAL_SIZE 39
#define SW_HTTP_SERVER_BOUNDARY_PREKEY "SwooleBoundary"

namespace candidate {
// The random part of the caller's boundary, in place of swoole_random_string's bytes.
static std::string random_part;
static void swoole_random_string(char *buf, size_t length) {
    memcpy(buf, random_part.data(), std::min(length, random_part.size()));
}

struct StaticHandler {
    swr_v2_http_context *context_;
    std::string mime;
    bool modified = false;
    const std::string &get_mimetype() const { return mime; }
    bool is_modified_range(const std::string &) const { return modified; }
    uint32_t ensure_boundary();
    void parse_range(const char *range, const char *if_range);
};
#include "http_range_candidate.inc"
}  // namespace candidate

extern "C" {
// See swoole_rs_oracle::http_range::Outcome.
struct swr_oracle_http_range {
    size_t content_length;
    int32_t status_code, thrown;
    size_t tasks, end_part_length;
    char end_part[128];
};

void swr_oracle_http_range_candidate(const char *range, uint64_t filesize, const char *mime, const char *boundary,
                                     int if_range, int modified, swr_oracle_http_range *out, void *tasks_out,
                                     size_t capacity) {
    static const char url[] = "/file";
    candidate::StaticHandler handler{swr_v2_http_context_new(reinterpret_cast<const uint8_t *>(url), 5, 4096)};
    *out = {};
    if (!handler.context_) {
        out->thrown = 1;
        return;
    }
    swr_v2_http_observation file{};
    file.filesize = filesize;
    swr_v2_http_context_observed(handler.context_, 0, &file);
    handler.mime = mime;
    handler.modified = modified;
    const size_t prefix = sizeof(SW_HTTP_SERVER_BOUNDARY_PREKEY) - 1;
    candidate::random_part = strlen(boundary) > prefix ? boundary + prefix : "";
    try {
        handler.parse_range(range, if_range ? "" : nullptr);
    } catch (const std::exception &) {
        out->thrown = 1;
    }
    swr_v2_http_observation facts{};
    swr_v2_http_context_observe(handler.context_, &facts);
    out->content_length = facts.content_length;
    out->status_code = facts.status;
    out->tasks = facts.task_count;
    size_t length = 0;
    swr_v2_http_context_text(handler.context_, SWR_HTTP_CONTEXT_END, nullptr, 0, &length);
    out->end_part_length = length;
    swr_v2_http_context_text(handler.context_, SWR_HTTP_CONTEXT_END, reinterpret_cast<uint8_t *>(out->end_part),
                             std::min(length, sizeof(out->end_part)), &length);
    std::vector<swr_v2_http_static_task> tasks(facts.task_count);
    size_t written = 0;
    swr_v2_http_context_tasks(handler.context_, tasks.data(), tasks.size(), &written);
    auto *task = static_cast<char *>(tasks_out);
    for (size_t i = 0; i < written && i < capacity; i++) {
        uint64_t offset = tasks[i].offset, size = tasks[i].length;
        memcpy(task, &offset, 8);
        memcpy(task + 8, &size, 8);
        memset(task + 16, 0, SW_HTTP_SERVER_PART_HEADER);
        memcpy(task + 16, tasks[i].part_header, strnlen(tasks[i].part_header, SW_HTTP_SERVER_PART_HEADER));
        task += 16 + SW_HTTP_SERVER_PART_HEADER;
    }
    swr_v2_http_context_drop(handler.context_);
}
}
