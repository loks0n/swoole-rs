// Ordinary inert queue consumers only. Never constructs/destroys an actual
// production Reactor or invokes its destructor/shutdown path.
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <list>
#include <utility>
#include <vector>
#include "swoole_rs_reactor.h"
#include "swoole_rs_reactor_defer.h"
#include "callback-queues.inc"
int main() {
    unsigned checks=0;auto check=[&](bool v){assert(v);++checks;};
    for(unsigned count:{0u,1u,17u,65u}) {
        swoole::Reactor model;std::vector<unsigned> values;
        for(unsigned i=0;i<count;++i) {
            swoole::Callback function=[i](void *data){static_cast<std::vector<unsigned> *>(data)->push_back(i);};
            model.add_destroy_callback(function,&values);
            function=[](void *){}; // Queue must retain its own ordinary value copy.
        }
        check(values.empty());
        model.destroy_callbacks.execute(); // Inert FIFO, NOT Reactor destruction.
        check(values.size()==count);
        for(unsigned i=0;i<count;++i)check(values[i]==i);
        model.destroy_callbacks.execute();check(values.size()==count);
        model.add_destroy_callback([](void *data){static_cast<std::vector<unsigned> *>(data)->push_back(99);},&values);
        model.destroy_callbacks.execute();check(values.size()==count+1);check(values.back()==99);
        // Empty normal member cleanup only; no nonempty/custom destructor observer.
    }
    std::cout<<"{\"inert_queue_cases\":4,\"checks\":"<<checks<<",\"actual_reactor_destructor_executed\":false,\"custom_destruction_or_reentry\":false,\"allocation_fault_probes\":false}\n";
}
