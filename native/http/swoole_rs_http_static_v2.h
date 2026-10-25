#ifndef SWOOLE_RS_HTTP_STATIC_V2_H
#define SWOOLE_RS_HTTP_STATIC_V2_H
#include "swoole_static_handler.h"
#include "swoole_rs_http_context.h"
#include "swoole_rs_http_rewrite_store.h"

namespace swoole {
namespace http_server {
// Unreleased selected facade. Sole metadata/container custody is Rust; native
// retains only external server/configuration views, never mirrored context.
class StaticHandlerV2 {
    Server *serv_;
    const RewriteRulesField *rules_;
    swr_v2_http_context *context_;
    swr_v2_http_observation observe() const;
    std::string text(uint32_t kind) const;
    bool stat_file();
    bool set_filename();
    uint32_t ensure_boundary();
    bool is_modified_range(const std::string &date) const;

  public:
    StaticHandlerV2(Server *server, const char *url, size_t length,
                    const RewriteRulesField *rules);
    ~StaticHandlerV2();
    StaticHandlerV2(const StaticHandlerV2 &) = delete;
    StaticHandlerV2 &operator=(const StaticHandlerV2 &) = delete;
    bool get_dir_files();
    bool try_serve_index_file();
    size_t make_index_page(String *buffer);
    bool try_serve();
    static std::string get_date() { return StaticHandler::get_date(); }
    std::string get_date_last_modified() const;
    bool is_modified(const std::string &date) const;
    bool has_index_file() const;
    bool is_enabled_auto_index() const;
    bool is_dir() const;
    void parse_range(const char *range, const char *condition);
    std::vector<swr_v2_http_static_task> copy_tasks() const;
    size_t get_content_length() const;
    const std::string &get_mimetype() const;
    const std::string &get_content_type(std::string &scratch);
    size_t get_filesize() const;
    time_t get_file_mtime() const;
    int32_t get_status() const;
    // Copies into scoped native IO storage; no Rust pointer escapes.
    void copy_filename(char *output, size_t capacity) const;
    size_t copy_end_part(char *output, size_t capacity) const;
};
}
}
#endif
