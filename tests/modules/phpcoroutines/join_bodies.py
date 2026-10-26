"""Sole Rust join-set/shared flag metadata, Native callbacks and payloads retained."""
SIGNATURE = 'static PHP_METHOD(swoole_coroutine, join) {'
OWNER = r'''class PHPCoroutineJoinMetadata {
    swr_phpcoroutines_join_owner *owner;
  public:
    PHPCoroutineJoinMetadata() : owner(swr_v1_phpcoroutines_join_try_new()) {
        if (!owner) { throw std::bad_alloc(); }
    }
    PHPCoroutineJoinMetadata(const PHPCoroutineJoinMetadata &other) noexcept : owner(other.owner) {
        if (owner && !swr_v1_phpcoroutines_join_clone(owner)) { std::terminate(); }
    }
    PHPCoroutineJoinMetadata(PHPCoroutineJoinMetadata &&other) noexcept : owner(other.owner) {
        other.owner = nullptr;
    }
    ~PHPCoroutineJoinMetadata() {
        if (owner) { swr_v1_phpcoroutines_join_drop(owner); }
    }
    PHPCoroutineJoinMetadata &operator=(const PHPCoroutineJoinMetadata &) = delete;
    PHPCoroutineJoinMetadata &operator=(PHPCoroutineJoinMetadata &&) = delete;
    const swr_phpcoroutines_join_owner *identity() const { return owner; }
    void insert(uintptr_t token) const {
        if (!swr_v1_phpcoroutines_join_try_insert(owner, token)) { throw std::bad_alloc(); }
    }
    bool erase_empty(uintptr_t token) const { return swr_v1_phpcoroutines_join_erase_empty(owner, token); }
    bool empty() const { return swr_v1_phpcoroutines_join_empty(owner); }
    bool next(size_t *cursor, uintptr_t *token) const { return swr_v1_phpcoroutines_join_next(owner, cursor, token); }
    void cancel() const { swr_v1_phpcoroutines_join_cancel(owner); }
    bool can_resume() const { return swr_v1_phpcoroutines_join_can_resume(owner); }
 };
class PHPCoroutineJoinMembership {
    const swr_phpcoroutines_join_owner *owner = nullptr;
  public:
    PHPCoroutineJoinMembership() = default;
    PHPCoroutineJoinMembership(const PHPCoroutineJoinMembership &) = delete;
    PHPCoroutineJoinMembership &operator=(const PHPCoroutineJoinMembership &) = delete;
    void bind(const PHPCoroutineJoinMetadata &metadata) noexcept {
        owner = metadata.identity();
        if (!swr_v1_phpcoroutines_join_clone(owner)) { std::terminate(); }
    }
    ~PHPCoroutineJoinMembership() {
        if (owner) {
            swr_v1_phpcoroutines_join_release_membership(owner);
            swr_v1_phpcoroutines_join_drop(owner);
        }
    }
};''' 


