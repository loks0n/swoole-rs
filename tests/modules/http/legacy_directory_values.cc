// Ordinary initialized value operations only; no full StaticHandler lifetime.
#include "swoole_rs_http_legacy_directory.h"
#include <stdexcept>
static size_t check_directory_values() {
    using swoole::http_server::LegacyDirectory;
    size_t checks=0;
    auto require=[&](bool value){++checks;if(!value)throw std::runtime_error("directory value mismatch");};
    LegacyDirectory empty;
    empty.scan_finish();
    LegacyDirectory empty_copy(empty);
    require(empty.empty() && empty_copy.empty());
    for (unsigned count:{1u,17u,65u,257u}) {
        LegacyDirectory original;
        std::set<std::string> expected;
        for (unsigned i=count;i--;) {
            auto name="value-"+std::to_string(i)+"-é&.txt";
            original.insert(name.c_str());original.insert(name.c_str());expected.insert(name);
            name.assign("reused input");
        }
        auto equal=[&](const LegacyDirectory &value){
            require(value.size()==expected.size());
            for(const auto &name:expected)require(value.contains(name));
            require(!value.contains("missing"));
        };
        LegacyDirectory scanned;
        for (auto i=expected.rbegin();i!=expected.rend();++i) {
            auto name=*i;
            scanned.scan_append(name.c_str());scanned.scan_append(name.c_str());
            name.assign("reused scan input");
        }
        scanned.scan_finish();equal(scanned);
        LegacyDirectory copied(original);equal(copied);
        copied.insert("only-copy");require(copied.contains("only-copy")&&!original.contains("only-copy"));
        LegacyDirectory assigned;assigned.insert("old");assigned=original;equal(assigned);
        assigned=assigned;equal(assigned);
        LegacyDirectory moved(std::move(assigned));equal(moved);
        require(assigned.empty());assigned.insert("reusable-moved-value");
        require(assigned.contains("reusable-moved-value")&&!moved.contains("reusable-moved-value"));
        LegacyDirectory destination;destination.insert("discarded");destination=std::move(moved);equal(destination);
        require(moved.empty());equal(original);
        const std::vector<std::string> priority={"missing",*expected.rbegin(),*expected.begin()};
        require(original.intersection(priority)==priority[1]);
    }
    return checks;
}
