/* C11 ABI/layout and inert raw-token linkage only; no Native payload/effects. */
#include "swoole_rs_phpevents.h"
#include <assert.h>
_Static_assert(sizeof(SwrPhpEventCallback) == sizeof(void *), "callback width");
_Static_assert(_Alignof(SwrPhpEventCallback) == _Alignof(void *), "callback alignment");
_Static_assert(sizeof(SwrPhpEventMethod) == sizeof(SwrPhpEventAlias) + 2 * sizeof(uint32_t), "catalogue POD width");
_Static_assert(offsetof(SwrPhpEventMethod, alias) == 0, "catalogue alias prefix");
_Static_assert(offsetof(SwrPhpEventMethod, flags) == offsetof(SwrPhpEventMethod, handler) + sizeof(uint32_t), "catalogue flags offset");
int main(void) {
    SwrPhpEventRegistry *registry = NULL;
    assert(swr_v1_phpevents_registry_try_insert(&registry, 7, 29) == 0);
    assert(swr_v1_phpevents_registry_try_insert(&registry, 7, 41) == 0);
    assert(swr_v1_phpevents_registry_contains(registry, 7));
    assert(swr_v1_phpevents_registry_get(registry, 7) == 41);
    swr_v1_phpevents_registry_drop(registry);

    SwrPhpEventMethod method;
    SwrPhpEventAlias alias;
    for (size_t index = 0; index < 11; ++index) {
        assert(swr_v1_phpevents_catalogue(index, 1, 0x100, 0x40, &method));
        assert(swr_v1_phpevents_alias(index, &alias));
        assert(alias.method == method.alias.method && alias.function == method.alias.function);
        assert(alias.method_length == method.alias.method_length && alias.function_length == method.alias.function_length);
        assert(method.flags == 0x140 && method.handler < 11);
    }
    const char *saved = method.alias.method;
    assert(!swr_v1_phpevents_catalogue(11, 0, 1, 2, &method));
    assert(method.alias.method == saved);
    assert(!swr_v1_phpevents_catalogue(0, 0, 1, 2, NULL));

    SwrPhpEventCallback read, write;
    uint32_t phase = 0;
    uintptr_t identity = 0;
    assert(swr_v1_phpevents_callbacks(&phase, SWR_EVENT_CALLBACK_SEED,
           &read, &write, 17, 29, &identity) == 0);
    assert(swr_v1_phpevents_callbacks(&phase, SWR_EVENT_CALLBACK_READ,
           &read, &write, 0, 0, &identity) == 2 && identity == 17);
    assert(swr_v1_phpevents_callbacks(&phase, SWR_EVENT_CALLBACK_WRITE,
           &read, &write, 0, 0, &identity) == 2 && identity == 29);
    /* No replacement/deferral/backend executes: both constructors returned null. */
    phase = 0;
    assert(swr_v1_phpevents_update_owned(&phase, 1536, 0,
           &read, &write, 0, 0, &identity) == SWR_EVENT_UPDATE_CREATE_READ);
    assert(swr_v1_phpevents_update_owned(&phase, 1536, 0,
           &read, &write, 0, 0, &identity) == SWR_EVENT_UPDATE_CREATE_WRITE);
    assert(swr_v1_phpevents_update_owned(&phase, 1536, 0,
           &read, &write, 0, 0, &identity) == SWR_EVENT_UPDATE_BACKEND);
    assert(swr_v1_phpevents_update_owned(&phase, 1536, 0,
           &read, &write, 0, 0, &identity) == SWR_EVENT_UPDATE_TRUE);
    assert(read.identity == 17 && write.identity == 29);
    return 0;
}
