// Copied scalar branch facts only. No Zend/classloader/Coroutine/context/callback exists here.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
struct Facts { bool current, table, found, recursive; };
std::vector<uint32_t> reference(Facts facts) {
    std::vector<uint32_t> actions{SWR_CORO_AUTOLOAD_CURRENT};
    if (!facts.current) { actions.push_back(SWR_CORO_AUTOLOAD_DIRECT); return actions; }
    actions.push_back(SWR_CORO_AUTOLOAD_DELETE);
    if (!facts.table) actions.push_back(SWR_CORO_AUTOLOAD_INIT);
    actions.push_back(SWR_CORO_AUTOLOAD_LOOKUP);
    if (!facts.found) { actions.push_back(SWR_CORO_AUTOLOAD_OWNER); return actions; }
    actions.push_back(SWR_CORO_AUTOLOAD_RECURSION);
    actions.push_back(facts.recursive ? SWR_CORO_AUTOLOAD_NULL : SWR_CORO_AUTOLOAD_WAITER);
    return actions;
}
int main() {
    const Facts cases[] = {{false,false,false,false}, {true,false,false,false},
        {true,true,false,false}, {true,true,true,false}, {true,true,true,true}};
    for (const auto &facts : cases) {
        uint32_t state = 0;
        uint8_t observation = 0;
        std::vector<uint32_t> actions;
        for (unsigned bound = 0; ; ++bound) {
            assert(bound < 16);
            const auto action = swr_v1_phpcoroutines_autoload_policy(&state, observation);
            actions.push_back(action);
            if (action == SWR_CORO_AUTOLOAD_NULL || action == SWR_CORO_AUTOLOAD_DIRECT ||
                action == SWR_CORO_AUTOLOAD_WAITER || action == SWR_CORO_AUTOLOAD_OWNER) break;
            switch (action) {
            case SWR_CORO_AUTOLOAD_CURRENT: observation = facts.current; break;
            case SWR_CORO_AUTOLOAD_DELETE: observation = facts.table; break;
            case SWR_CORO_AUTOLOAD_LOOKUP: observation = facts.found; break;
            case SWR_CORO_AUTOLOAD_RECURSION: observation = facts.recursive; break;
            default: assert(action == SWR_CORO_AUTOLOAD_INIT);
            }
        }
        assert(actions == reference(facts));
    }
    std::cout << "five copied scalar branch routes; no native autoload or callbacks\n";
}
