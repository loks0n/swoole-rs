// Ordinary registration/lookup/removal metadata ONLY. Neither class is a
// swoole::Coroutine/Context, and no actual constructor, callback or yield runs.
#include "swoole_rs_coroutine.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <new>
#include <unordered_map>
#define sw_unlikely(value) (value)
#define sw_likely(value) (value)

struct NativeRegistration {
    using Coroutine=NativeRegistration;
    long cid;
    uint32_t marker;
    static long last_cid;
    static uint64_t peak_num;
    static bool activated;
    static size_t count_calls,activation_calls;
    static std::unordered_map<long,NativeRegistration *> coroutines;
    static size_t count() { ++count_calls;return coroutines.size(); }
    static void activate() { ++activation_calls;activated=true; }
    void register_metadata() {
#include "native-registration.inc"
    }
#include "native-cid.inc"
#include "native-lookup.inc"
    void remove_metadata() {
#include "native-remove.inc"
    }
};
long NativeRegistration::last_cid=0;
uint64_t NativeRegistration::peak_num=0;
bool NativeRegistration::activated=false;
size_t NativeRegistration::count_calls=0,NativeRegistration::activation_calls=0;
std::unordered_map<long,NativeRegistration *> NativeRegistration::coroutines;

struct SelectedRegistration {
    using Coroutine=SelectedRegistration;
    swr_v1_coroutine_cid cid; // no initializer; raw Rust publication precedes use
    uint32_t marker;
    static swr_v1_coroutine_scheduler scheduler_;
    static size_t count_calls,activation_calls;
    static std::unordered_map<long,SelectedRegistration *> coroutines;
    static size_t count() { ++count_calls;return coroutines.size(); }
    static void activate() {
        ++activation_calls;
        swr_v1_coroutine_scheduler_set_active(&scheduler_,1);
    }
    void register_metadata() {
#include "selected-registration.inc"
    }
#include "selected-cid.inc"
#include "selected-lookup.inc"
    void remove_metadata() {
#include "selected-remove.inc"
    }
};
swr_v1_coroutine_scheduler SelectedRegistration::scheduler_={65536,0,0,0,0};
size_t SelectedRegistration::count_calls=0,SelectedRegistration::activation_calls=0;
std::unordered_map<long,SelectedRegistration *> SelectedRegistration::coroutines;

int main() {
    size_t observations=0;
    for (long seed: {-17L,-1L,200L}) {
        std::array<NativeRegistration,64> native;
        std::array<SelectedRegistration,64> selected;
        NativeRegistration::coroutines.clear();SelectedRegistration::coroutines.clear();
        NativeRegistration::last_cid=seed;NativeRegistration::peak_num=0;NativeRegistration::activated=false;
        NativeRegistration::count_calls=NativeRegistration::activation_calls=0;
        SelectedRegistration::scheduler_={65536,seed,0,0,0};
        SelectedRegistration::count_calls=SelectedRegistration::activation_calls=0;
        for (size_t index=0;index<native.size();index++) {
            if (index==8) {
                // Existing-key overwrite, not a reset-to-null or node replacement.
                NativeRegistration::last_cid=seed;SelectedRegistration::scheduler_.last_cid=seed;
            }
            if (index==32) {
                // Only the inert activation bit changes; no actual activation.
                NativeRegistration::activated=false;SelectedRegistration::scheduler_.activated=0;
            }
            native[index].marker=selected[index].marker=static_cast<uint32_t>(index+1);
            native[index].register_metadata();selected[index].register_metadata();
            assert(native[index].get_cid()==selected[index].get_cid());++observations;
            assert(NativeRegistration::last_cid==SelectedRegistration::scheduler_.last_cid);++observations;
            assert(NativeRegistration::peak_num==SelectedRegistration::scheduler_.peak_num);++observations;
            assert(NativeRegistration::activated==(SelectedRegistration::scheduler_.activated!=0));++observations;
            assert(NativeRegistration::activation_calls==SelectedRegistration::activation_calls);++observations;
            assert(NativeRegistration::coroutines.size()==SelectedRegistration::coroutines.size());++observations;
            assert(NativeRegistration::count_calls==SelectedRegistration::count_calls);
            ++observations;
            for (long key=seed-2;key<=seed+70;key++) {
                auto *a=NativeRegistration::get_by_cid(key);
                auto *b=SelectedRegistration::get_by_cid(key);
                assert((a!=nullptr)==(b!=nullptr));++observations;
                if (a) { assert(a->marker==b->marker);++observations; }
            }
        }
        // Preserve the public lookup's absent/stored-null equivalence.
        NativeRegistration::coroutines[seed+1]=nullptr;
        SelectedRegistration::coroutines[seed+1]=nullptr;
        assert(NativeRegistration::get_by_cid(seed+1)==nullptr);
        assert(SelectedRegistration::get_by_cid(seed+1)==nullptr);observations+=2;
        for (size_t index=0;index<native.size();index+=3) {
            const long native_saved=native[index].get_cid(),selected_saved=selected[index].get_cid();
            native[index].remove_metadata();selected[index].remove_metadata();
            assert(native_saved==selected_saved);++observations;
            assert(NativeRegistration::get_by_cid(native_saved)==nullptr);
            assert(SelectedRegistration::get_by_cid(selected_saved)==nullptr);observations+=2;
            assert(NativeRegistration::coroutines.size()==SelectedRegistration::coroutines.size());++observations;
        }
        NativeRegistration::coroutines.clear();SelectedRegistration::coroutines.clear();
    }
    std::printf("{\"scenarios\":3,\"registrations\":192,\"observations\":%zu,\"actual_Coroutine_or_Context\":false,\"callback_invoked\":false}\n",observations);
}
