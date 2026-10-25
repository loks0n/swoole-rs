#ifndef SWOOLE_RS_HTTP_LEGACY_DIRECTORY_H
#define SWOOLE_RS_HTTP_LEGACY_DIRECTORY_H
#if defined(SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE) && SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE && \
    (!defined(SWOOLE_RS_HTTP) || !SWOOLE_RS_HTTP)
#error "Rust Legacy directory storage requires selected Rust HTTP"
#endif
#include "swoole_rs_http_context.h"
#include <set>
#include <string>
#include <new>
#include <stdexcept>
#include <utility>
#include <vector>
#ifdef __cplusplus
namespace swoole { namespace http_server {
class StaticConfig;
class alignas(std::set<std::string>) LegacyDirectory {
    friend class StaticConfig;
    static_assert(sizeof(std::set<std::string>) > sizeof(void *), "directory reserve needs a representable native slot");
    swr_v2_http_directory *owner_ = nullptr;
    // Explicit reserved representation, never a live std::set object.
    unsigned char reserved_[sizeof(std::set<std::string>)-sizeof(owner_)]{};
    void ensure_owner() {
        if (!owner_) {
            owner_=swr_v2_http_directory_new();
            if (!owner_) throw std::bad_alloc();
        }
    }
    static void checked(int32_t result) {
        if (result == -3) throw std::bad_alloc();
        if (result < 0) throw std::logic_error("Invalid directory state");
    }
  public:
    LegacyDirectory() noexcept = default;
    ~LegacyDirectory() { (void) reserved_; swr_v2_http_directory_drop(owner_); }
    LegacyDirectory(const LegacyDirectory &other) {
        checked(swr_v2_http_directory_clone(other.owner_,&owner_));
    }
    LegacyDirectory &operator=(const LegacyDirectory &other) {
        if (this != &other) { LegacyDirectory copy(other); swap(copy); }
        return *this;
    }
    LegacyDirectory(LegacyDirectory &&other) noexcept : owner_(other.owner_) { other.owner_=nullptr; }
    LegacyDirectory &operator=(LegacyDirectory &&other) noexcept {
        if (this != &other) {
            swr_v2_http_directory_drop(owner_); owner_=other.owner_; other.owner_=nullptr;
        }
        return *this;
    }
    void swap(LegacyDirectory &other) noexcept { std::swap(owner_,other.owner_); }
    bool empty() const { return size()==0; }
    size_t size() const { return swr_v2_http_directory_count(owner_); }
    void insert(const char *name) {
        ensure_owner();
        checked(swr_v2_http_directory_insert(owner_,reinterpret_cast<const uint8_t *>(name),std::char_traits<char>::length(name)));
    }
    void scan_append(const char *name) {
        ensure_owner();
        const auto result=swr_v2_http_directory_scan_append(owner_,
            reinterpret_cast<const uint8_t *>(name),std::char_traits<char>::length(name));
        // Publish a finalized partial value before Native error translation.
        // This source boundary is not allocation-failure/reentry qualification.
        if (result < 0) swr_v2_http_directory_scan_finish(owner_);
        checked(result);
    }
    void scan_finish() { swr_v2_http_directory_scan_finish(owner_); }
    std::string intersection(const std::vector<std::string> &indexes) const {
        for (const auto &name:indexes) if (contains(name)) return name;
        return {};
    }
    bool contains(const std::string &name) const {
        const auto result=swr_v2_http_directory_contains(owner_,reinterpret_cast<const uint8_t *>(name.data()),name.size());
        checked(result); return result!=0;
    }
    int32_t emit(size_t index, const swr_v1_http_index_page_input &page, uint8_t *buffer,
                 size_t length, size_t capacity, swr_v2_http_page_buffer *result) const {
        // Rust renders owned names and returns before Native buffer effects.
        return swr_v2_http_directory_emit(owner_,index,&page,buffer,length,capacity,result);
    }
};
static_assert(sizeof(LegacyDirectory)==sizeof(std::set<std::string>),"directory physical slot");
static_assert(alignof(LegacyDirectory)==alignof(std::set<std::string>),"directory physical alignment");
}}

#endif
#endif
