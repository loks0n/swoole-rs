/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include "swoole_rs_clients.h"
#include <new>
#include <string>

// Module-private RAII for the sole Rust registry. No module-load heap/entropy.
// Dropping the owner frees Rust containers only, never native Client tokens.
class SwooleRustClientPool {
    void *handle = nullptr;
    static const uint8_t *data(const std::string &key) {
        return reinterpret_cast<const uint8_t *>(key.data());
    }
  public:
    SwooleRustClientPool() = default;
    SwooleRustClientPool(const SwooleRustClientPool &) = delete;
    SwooleRustClientPool &operator=(const SwooleRustClientPool &) = delete;
    ~SwooleRustClientPool() { swr_v1_clients_pool_destroy(handle); }
    struct swr_v1_clients_pool_state state(const std::string &key) const {
        return swr_v1_clients_pool_state(handle, data(key), key.size());
    }
    void *take(const std::string &key) {
        return swr_v1_clients_pool_take(handle, data(key), key.size());
    }
    void remove_empty(const std::string &key) {
        swr_v1_clients_pool_remove_empty(handle, data(key), key.size());
    }
    void push(const std::string &key, void *token) {
        if (!handle) {
            handle = swr_v1_clients_pool_create();
            if (!handle) throw std::bad_alloc();
        }
        if (swr_v1_clients_pool_push(handle, data(key), key.size(), token) != 0) {
            throw std::bad_alloc();
        }
    }
};
