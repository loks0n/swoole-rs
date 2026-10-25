// Independent positive entrypoint; the historical interruption/destructor
// matrices are not included or executed. Native APIs remain inert recorders.
#include "common-positive-model.inc"
int main() {
    (void) &named_call; // Keep the unchanged fixture declaration warning-clean.
    size_t merges = 0, calls = 0;
    fail_at = -1;
    for (bool num : {false, true}) for (bool add_ok : {false, true}) for (bool array : {false, true}) {
        numeric = num;
        inserted = add_ok;
        const auto before = merge(reference::array_add_or_merge, array);
        const auto after = merge(candidate::array_add_or_merge, array);
        assert(before == after);
        assert(before.find("throw;") == std::string::npos);
        ++merges;
    }
    publish_exception = false;
    for (bool coroutine : {false, true}) for (bool storage : {false, true}) {
        call_result = coroutine ? 11 : 0;
        const auto before = call(reference::function::call, coroutine, storage);
        const auto after = call(candidate::function::call, coroutine, storage);
        assert(before == after);
        assert(before.find("throw;") == std::string::npos);
        assert(before.find("return:1;") != std::string::npos);
        ++calls;
    }
    std::cout << "{\"positive_merges\":" << merges << ",\"positive_calls\":" << calls
              << ",\"historical_failure_matrix_executed\":false,\"native_runtime_executed\":false}\n";
}
