#ifndef SWOOLE_RS_COROUTINE_REGISTRY_H
#define SWOOLE_RS_COROUTINE_REGISTRY_H

#include <cstddef>
#include <cstdint>
#include <new>
#include <utility>
#include "swoole_rs_coroutine.h"
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
#include <unordered_map>
#if !defined(__APPLE__) || !defined(_LIBCPP_VERSION) || _LIBCPP_VERSION != 210106 || _LIBCPP_ABI_VERSION != 1
#error "Coroutine registry ON requires Apple libc++210106 ABI1 live order; unknown policies remain OFF"
#endif
static_assert(sizeof(long) == 8 && sizeof(size_t) == 8, "Coroutine registry long-key/hash ABI");
#endif

// Additive local bridge; seven shared legacy declarations remain frozen.
#include "swoole_rs_coroutine_registry_policy.h"

namespace swoole {
// Selected SDK view only. Rust owns entries and tokens; Native owns objects.
// Known first-party range/find/count/insert/erase consumers are supported. This
// is not std::unordered_map binary/source compatibility for external consumers.
// Apple libc++210106 ABI1 live order is modeled; unknown ON policies refuse.
template<class T> class RustCoroutineRegistry {
    void *owner_ = nullptr;
    static constexpr swr_v1_coroutine_registry_policy native_policy() {
        // The exact Apple compiler guard above remains mandatory for ON. No
        // Rust target-OS inference and no GNU/unknown capability admission.
#if defined(__APPLE__) && defined(_LIBCPP_VERSION) && defined(_LIBCPP_ABI_VERSION)
        return {1, _LIBCPP_VERSION, _LIBCPP_ABI_VERSION};
#else
        return {0, 0, 0}; // Not a qualified Native compiler/stdlib capsule.
#endif
    }
  public:
    class iterator {
        const void *entry_ = nullptr;
        std::pair<long, T *> value_{0, nullptr};
        void refresh() {
            auto value = swr_v1_coroutine_registry_item(entry_);
            value_.first = value.cid;
            value_.second = reinterpret_cast<T *>(value.token);
        }
      public:
        iterator() = default;
        explicit iterator(const void *entry) : entry_(entry) { refresh(); }
        std::pair<long, T *> &operator*() { refresh(); return value_; }
        std::pair<long, T *> *operator->() { refresh(); return &value_; }
        iterator &operator++() {
            entry_ = swr_v1_coroutine_registry_item(entry_).next;
            refresh();
            return *this;
        }
        bool operator==(const iterator &other) const { return entry_ == other.entry_; }
        bool operator!=(const iterator &other) const { return !(*this == other); }
    };
    class slot {
        RustCoroutineRegistry &registry_;
        long cid_;
      public:
        slot(RustCoroutineRegistry &registry, long cid) : registry_(registry), cid_(cid) {
            // Native operator[] publishes a null miss before the assignment.
            if (swr_v1_coroutine_registry_find(registry_.owner_, cid_) == nullptr &&
                swr_v1_coroutine_registry_selected_insert(&registry_.owner_, cid_, 0, native_policy()) != 0) {
                throw std::bad_alloc();
            }
        }
        operator T *() const {
            auto entry = swr_v1_coroutine_registry_find(registry_.owner_, cid_);
            return reinterpret_cast<T *>(swr_v1_coroutine_registry_item(entry).token);
        }
        slot &operator=(T *value) {
            if (swr_v1_coroutine_registry_selected_insert(&registry_.owner_, cid_, reinterpret_cast<uintptr_t>(value), native_policy()) != 0) {
                throw std::bad_alloc(); // Native exception, after Rust returned.
            }
            return *this;
        }
    };
    constexpr RustCoroutineRegistry() noexcept = default;
    RustCoroutineRegistry(const RustCoroutineRegistry &) = delete;
    RustCoroutineRegistry &operator=(const RustCoroutineRegistry &) = delete;
    ~RustCoroutineRegistry() { swr_v1_coroutine_registry_drop(&owner_); }
    slot operator[](long cid) { return slot(*this, cid); }
    iterator begin() const { return iterator(swr_v1_coroutine_registry_first(owner_)); }
    iterator end() const { return iterator(); }
    iterator find(long cid) const { return iterator(swr_v1_coroutine_registry_find(owner_, cid)); }
    void clear() { swr_v1_coroutine_registry_clear(owner_); }
    size_t size() const { return swr_v1_coroutine_registry_count(owner_); }
    T *lookup(long cid) const {
        return reinterpret_cast<T *>(swr_v1_coroutine_registry_lookup(owner_, cid));
    }
    swr_v1_coroutine_creation_action creation_step(swr_v1_coroutine_creation_cursor *cursor,
                                                  swr_v1_coroutine_scheduler *scheduler,
                                                  swr_v1_coroutine_cid *cid, T *token, size_t count) {
        return swr_v1_coroutine_selected_create_step(cursor, scheduler, cid, &owner_, reinterpret_cast<uintptr_t>(token), count, native_policy());
    }
    swr_v1_coroutine_registry_print_action print_step(swr_v1_coroutine_registry_print_cursor *cursor,
                                                       const T *object, size_t status_offset) const {
        return swr_v1_coroutine_registry_print_step(owner_, cursor, object, status_offset);
    }
    size_t unregister(const swr_v1_coroutine_cid *cid) {
        return swr_v1_coroutine_unregister(owner_, cid);
    }
    size_t erase(long cid) {
        return swr_v1_coroutine_registry_erase(owner_, cid);
    }
};
} // namespace swoole
#endif
