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


def replace_join(source, result, body):
    original = body(source, SIGNATURE)
    old = '''    std::set<PHPContext *> co_set;
    std::shared_ptr<bool> canceled = std::make_shared<bool>(false);'''
    if original.count(old) != 1:
        raise ValueError('Pinned join owner declarations changed')
    selected = original.replace(old, '    PHPCoroutineJoinMembership membership;\n    PHPCoroutineJoinMetadata metadata;\n    membership.bind(metadata);')
    selected = selected.replace('[&co_set, canceled, co]', '[metadata, co]')
    old = '''        co_set.erase(task);
        if (!co_set.empty()) {'''
    if selected.count(old) != 1:
        raise ValueError('Pinned join erase/empty order changed')
    selected = selected.replace(old, '        if (!metadata.erase_empty(reinterpret_cast<uintptr_t>(task))) {')
    selected = selected.replace('[co, canceled]', '[co, metadata]').replace('if (*canceled == false)', 'if (metadata.can_resume())')
    selected = selected.replace('co_set.insert(ctx);', 'metadata.insert(reinterpret_cast<uintptr_t>(ctx));')
    selected = selected.replace('if (co_set.empty())', 'if (metadata.empty())')
    old = '''        if (!co_set.empty()) {
            for (auto ctx : co_set) {
                ctx->on_close = nullptr;
            }
        }
        *canceled = true;'''
    new = '''        size_t cursor = 0;
        uintptr_t token = 0;
        while (metadata.next(&cursor, &token)) {
            auto *ctx = reinterpret_cast<PHPContext *>(token);
            ctx->on_close = nullptr;
        }
        metadata.cancel();'''
    if selected.count(old) != 1:
        raise ValueError('Pinned join cleanup/canceled order changed')
    selected = selected.replace(old, new)
    if any(text in selected for text in ('co_set', 'shared_ptr', 'make_shared', '*canceled')):
        raise ValueError('Native join metadata mirror remains')
    result = result.replace(SIGNATURE + original + '}', SIGNATURE + '\n#ifdef SWOOLE_RS_PHPCOROUTINES' + selected + '#else' + original + '#endif\n}')
    result = result.replace('#include <new>', '#include <new>\n#include <exception>', 1)
    return result.replace(SIGNATURE, '#ifdef SWOOLE_RS_PHPCOROUTINES\n' + OWNER + '\n#endif\n\n' + SIGNATURE, 1)
