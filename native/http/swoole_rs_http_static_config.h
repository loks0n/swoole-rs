#ifndef SWOOLE_RS_HTTP_STATIC_CONFIG_H
#define SWOOLE_RS_HTTP_STATIC_CONFIG_H
#include "swoole_rs_http_context.h"
#if defined(SWOOLE_RS_HTTP_STATIC_CONFIG) && SWOOLE_RS_HTTP_STATIC_CONFIG && \
    (!defined(SWOOLE_RS_HTTP) || !SWOOLE_RS_HTTP)
#error "Rust static configuration requires selected Rust HTTP"
#endif
#ifdef __cplusplus
extern "C" {
#endif
typedef struct swr_v2_http_static_config swr_v2_http_static_config;
enum swr_v2_http_config_operation {
    SWR_HTTP_CONFIG_ROOT=0, SWR_HTTP_CONFIG_LOCATION=1, SWR_HTTP_CONFIG_INDEX=2,
    SWR_HTTP_CONFIG_INITIALIZE=3
};
enum swr_v2_http_config_root_action {
    SWR_HTTP_CONFIG_ROOT_DONE=0, SWR_HTTP_CONFIG_ROOT_REALPATH=1,
    SWR_HTTP_CONFIG_ROOT_WARN_LENGTH=2, SWR_HTTP_CONFIG_ROOT_WARN_DIRECTORY=3
};
int32_t swr_v2_http_config_apply(swr_v2_http_static_config **, uint32_t,
    const swr_v1_http_proxy_text *);
void swr_v2_http_config_drop(swr_v2_http_static_config *);
int32_t swr_v2_http_config_root_step(swr_v2_http_static_config **, size_t, size_t,
    uint32_t, const swr_v1_http_proxy_text *);
int32_t swr_v2_http_config_path(const swr_v2_http_static_config *, const swr_v1_http_proxy_text *,
    uint8_t *, size_t, swr_v1_http_static_path_state *, uint32_t *);
int32_t swr_v2_http_config_contains(const swr_v2_http_static_config *, const swr_v1_http_proxy_text *);
int32_t swr_v2_http_config_select_index(const swr_v2_http_static_config *,
    const swr_v1_http_proxy_text *, size_t, uint8_t *, size_t, size_t *);
int32_t swr_v2_http_config_directory_index(const swr_v2_http_static_config *,
    const swr_v2_http_directory *, uint8_t *, size_t, size_t *);
int32_t swr_v2_http_config_legacy_index(const swr_v2_http_static_config *, uint32_t *, uint32_t);
int32_t swr_v2_http_config_serve(const swr_v2_http_static_config *, swr_v2_http_context *,
    const swr_v2_http_serve_observation *);
int32_t swr_v2_http_config_index(const swr_v2_http_static_config *, swr_v2_http_context *,
    uint32_t, size_t, size_t *);
#ifdef __cplusplus
}
#include <cstring>
#include <new>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#if defined(SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE) && SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE
#include "swoole_rs_http_legacy_directory.h"
#endif
namespace swoole {
namespace http_server {
// Server is already noncopyable through its mutex members. This is one lazy
// Rust owner, not a std-container representation or a Native root/name cache.
class StaticConfig {
    swr_v2_http_static_config *owner_ = nullptr;
    static int32_t checked(int32_t result) {
        if (result == -3) throw std::bad_alloc();
        if (result < 0) throw std::logic_error("Invalid static configuration");
        return result;
    }
    void apply(uint32_t operation, const std::string &value) {
        const swr_v1_http_proxy_text input{reinterpret_cast<const uint8_t *>(value.data()),value.size()};
        checked(swr_v2_http_config_apply(&owner_,operation,&input));
    }
  public:
    StaticConfig() noexcept = default;
    ~StaticConfig() { swr_v2_http_config_drop(owner_); }
    StaticConfig(const StaticConfig &) = delete;
    StaticConfig &operator=(const StaticConfig &) = delete;
    void initialize() { checked(swr_v2_http_config_apply(&owner_,SWR_HTTP_CONFIG_INITIALIZE,nullptr)); }
    void add_location(const std::string &value) { apply(SWR_HTTP_CONFIG_LOCATION,value); }
    void add_index(const std::string &value) { apply(SWR_HTTP_CONFIG_INDEX,value); }
    int32_t root_begin(size_t requested, size_t limit) {
        return checked(swr_v2_http_config_root_step(&owner_,requested,limit,0,nullptr));
    }
    int32_t root_finish(const char *canonical) {
        const swr_v1_http_proxy_text input{reinterpret_cast<const uint8_t *>(canonical),
            canonical ? std::strlen(canonical) : 0};
        return checked(swr_v2_http_config_root_step(&owner_,0,0,1,canonical ? &input : nullptr));
    }
    int32_t path(const swr_v1_http_proxy_text &url, uint8_t *output, size_t capacity,
                 swr_v1_http_static_path_state *state, uint32_t *facts) const {
        return swr_v2_http_config_path(owner_,&url,output,capacity,state,facts);
    }
    bool contains(const char *filename, size_t length) const {
        const swr_v1_http_proxy_text input{reinterpret_cast<const uint8_t *>(filename),length};
        return checked(swr_v2_http_config_contains(owner_,&input)) != 0;
    }
    std::string select_index(const std::set<std::string> &directory) const {
        // One scoped immutable typed snapshot of the Legacy directory set.
        // Its strings stay Native-owned; no Rust span survives either call.
        std::vector<swr_v1_http_proxy_text> names;
        names.reserve(directory.size());
        for (const auto &name:directory)
            names.push_back({reinterpret_cast<const uint8_t *>(name.data()),name.size()});
        size_t count=0;
        checked(swr_v2_http_config_select_index(owner_,names.data(),names.size(),nullptr,0,&count));
        std::string value(count,'\0');
        if (count) checked(swr_v2_http_config_select_index(owner_,names.data(),names.size(),
            reinterpret_cast<uint8_t *>(&value[0]),value.size(),&count));
        return value;
    }
#if defined(SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE) && SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE
    std::string select_index(const LegacyDirectory &directory) const {
        size_t count=0;
        checked(swr_v2_http_config_directory_index(owner_,directory.owner_,nullptr,0,&count));
        std::string value(count,'\0');
        if (count) checked(swr_v2_http_config_directory_index(owner_,directory.owner_,
            reinterpret_cast<uint8_t *>(&value[0]),value.size(),&count));
        return value;
    }
#endif
    int32_t legacy_index(uint32_t *phase, uint32_t facts) const {
        return swr_v2_http_config_legacy_index(owner_,phase,facts);
    }
    int32_t serve(swr_v2_http_context *context, const swr_v2_http_serve_observation &observation) const {
        return swr_v2_http_config_serve(owner_,context,&observation);
    }
    int32_t index(swr_v2_http_context *context, uint32_t event, size_t value, size_t *cursor) const {
        return swr_v2_http_config_index(owner_,context,event,value,cursor);
    }
};
}
}
#endif
#endif
