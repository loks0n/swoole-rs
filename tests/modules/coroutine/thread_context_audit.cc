// Diagnostic native facade, NOT a configured production thread-context build.
// Actual pinned baton code runs with error-checking mutexes to expose ownership
// errors. Recording an error and returning changes its subsequent execution;
// this must never be classified as production feature parity or support.
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <functional>
#include <mutex>
#include <pthread.h>
#include <thread>
#include <vector>
static std::mutex audit_lock;
static std::vector<int> lock_errors, unlock_errors, destroy_errors;
static void record(std::vector<int> &errors, int code) {
    if (code) { std::lock_guard<std::mutex> guard(audit_lock); errors.push_back(code); }
}
struct CheckedMutex {
    pthread_mutex_t mutex;
    CheckedMutex() {
        pthread_mutexattr_t attr;
        assert(pthread_mutexattr_init(&attr)==0);
        assert(pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_ERRORCHECK)==0);
        assert(pthread_mutex_init(&mutex,&attr)==0);
        assert(pthread_mutexattr_destroy(&attr)==0);
    }
    ~CheckedMutex() { record(destroy_errors,pthread_mutex_destroy(&mutex)); }
    void lock() { record(lock_errors,pthread_mutex_lock(&mutex)); }
    void unlock() { record(unlock_errors,pthread_mutex_unlock(&mutex)); }
};
using CoroutineFunc=std::function<void(void *)>;
using coroutine_transfer_t=void *;
namespace swoole {
struct Reactor {};
struct Timer {};
struct TimerNode {};
struct String {};
struct AsyncThreads {};
struct ThreadGlobal {
    Reactor *reactor=nullptr;
    Timer *timer=nullptr;
    String *buffer_stack=nullptr;
    AsyncThreads *async_threads=nullptr;
};
static thread_local ThreadGlobal SwooleTG;
static bool swoole_timer_is_available() { return SwooleTG.timer!=nullptr; }
static void swoole_timer_add(long,bool,const std::function<void(Timer *,TimerNode *)>&,void*) {
    static Timer timer; SwooleTG.timer=&timer;
}
static void swoole_signal_block_all() {}
namespace coroutine {
struct Context {
    CoroutineFunc fn_;
    std::thread thread_;
    CheckedMutex lock_;
    CheckedMutex *swap_lock_;
    void *private_data_;
    bool end_;
    Context(size_t,CoroutineFunc,void *);
    ~Context();
    bool swap_in();
    bool swap_out();
    static void context_func(coroutine_transfer_t);
};
}
}
#define SW_USE_THREAD_CONTEXT 1
#include "actual-thread-context.inc"
int main() {
    using namespace swoole;
    using namespace swoole::coroutine;
    thread_context_init();
    bool executed=false;
    {
        Context context(65536,[&](void *) { executed=true; },nullptr);
        context.swap_in();
        // Destructor joins before reading the worker's observation.
    }
    assert(executed);
    delete SwooleTG.async_threads;
    SwooleTG.async_threads=nullptr;
    thread_context_clean();
    bool recursive=false, foreign=false;
    for(int error:lock_errors) recursive|=error==EDEADLK;
    for(int error:unlock_errors) foreign|=error==EPERM;
    assert(recursive && foreign);
    printf("native baton diagnostic: owner re-lock EDEADLK; foreign unlock EPERM; destroy errors=%zu\n",destroy_errors.size());
}
