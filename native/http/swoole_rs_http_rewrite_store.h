#ifndef SWOOLE_RS_HTTP_REWRITE_STORE_H
#define SWOOLE_RS_HTTP_REWRITE_STORE_H
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include "swoole_rs_http_context.h"

extern "C" {
struct swr_v2_http_rewrite_store;
struct swr_v2_http_rewrite_record {
    size_t pattern_length, replacement_length;
    uint32_t regex;
};
int32_t swr_v2_http_rewrite_store_add(swr_v2_http_rewrite_store **, const uint8_t *, size_t,
                                    const uint8_t *, size_t);
size_t swr_v2_http_rewrite_store_count(const swr_v2_http_rewrite_store *);
int32_t swr_v2_http_rewrite_store_read(const swr_v2_http_rewrite_store *, size_t,
                                     swr_v2_http_rewrite_record *, uint8_t *, size_t, uint8_t *, size_t);
int32_t swr_v2_http_rewrite_store_text(const swr_v2_http_rewrite_store *, size_t, uint32_t,
    uint8_t *, size_t, size_t *);
int32_t swr_v2_http_rewrite_store_literal(const swr_v2_http_rewrite_store *, size_t,
    const swr_v1_http_proxy_text *, uint8_t *, size_t, size_t *);
int32_t swr_v2_http_rewrite_store_context_literal(const swr_v2_http_rewrite_store *, size_t, swr_v2_http_context *);
int32_t swr_v2_http_rewrite_store_advance(const swr_v2_http_rewrite_store *, swr_v2_http_rewrite_state *,
    int32_t, const swr_v1_http_proxy_text *, size_t *, size_t *);
int32_t swr_v2_http_rewrite_store_context_advance(const swr_v2_http_rewrite_store *, swr_v2_http_context *, int32_t, size_t *);
void swr_v2_http_rewrite_store_drop(swr_v2_http_rewrite_store **);
}
namespace swoole {
namespace http_server {
struct RewriteRule;
// Replaces only the private Server field under the separate opt-in capability.
// No shared_ptr representation is inspected. The second slot is explicit ABI
// reserve, always null, never an owner/side table. Copies are forbidden just as
// Server copies are already forbidden by its mutex/thread members.
class RewriteRules {
    swr_v2_http_rewrite_store *owner_ = nullptr;
    void *abi_reserved_ = nullptr;
  public:
    RewriteRules() noexcept = default;
    ~RewriteRules() { (void) abi_reserved_; swr_v2_http_rewrite_store_drop(&owner_); }
    RewriteRules(const RewriteRules &) = delete;
    RewriteRules &operator=(const RewriteRules &) = delete;
    void append(const std::string &pattern, const std::string &replacement);
    size_t size() const { return swr_v2_http_rewrite_store_count(owner_); }
    swr_v2_http_rewrite_record inspect(size_t index) const;
    RewriteRule at(size_t index) const;
    std::string text(size_t index, uint32_t kind) const;
    int32_t advance(swr_v2_http_rewrite_state *, int32_t, const std::string &, size_t *, size_t *) const;
    int32_t advance(swr_v2_http_context *, int32_t, size_t *) const;
    int32_t literal(size_t index, const std::string &url, uint8_t *output, size_t capacity, size_t *written) const;
    int32_t literal(size_t index, swr_v2_http_context *context) const;
};
static_assert(sizeof(RewriteRules) == sizeof(std::shared_ptr<std::vector<RewriteRule>>),
              "rewrite store requires the legacy private field footprint");
static_assert(alignof(RewriteRules) == alignof(std::shared_ptr<std::vector<RewriteRule>>),
              "rewrite store requires the legacy private field alignment");
#if defined(SWOOLE_RS_HTTP_REWRITE_STORE) && SWOOLE_RS_HTTP_REWRITE_STORE
using RewriteRulesField = RewriteRules;
#else
using RewriteRulesField = std::shared_ptr<std::vector<RewriteRule>>;
#endif
}
}
#endif
