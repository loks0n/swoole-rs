// Real unchanged native Mutex/RWLock consumers of realtime_get/realtime_add.
#include "swoole_lock.h"
#include <cerrno>
#include <cstdlib>
#include <iostream>
#include <thread>

static void require(bool value) { if (!value) std::abort(); }

static void held_timeout(swoole::Lock &lock, int held, int waiting) {
    require(lock.lock(held) == 0);
    int result = -999;
    std::thread waiter([&] { result = lock.lock(waiting, 2); });
    waiter.join();
    require(result == ETIMEDOUT);
    require(lock.unlock() == 0);
    require(lock.lock(waiting, 10) == 0);
    require(lock.unlock() == 0);
}

int main() {
    swoole_init();
    {
        swoole::Mutex mutex(false);
        held_timeout(mutex, LOCK_EX, LOCK_EX);
#ifdef HAVE_RWLOCK
        swoole::RWLock rw(false);
        held_timeout(rw, LOCK_EX, LOCK_SH);
        held_timeout(rw, LOCK_SH, LOCK_EX);
#else
        return 2; // Missing capability is not a passing timed-lock gate.
#endif
    }
    swoole_clean();
    std::cout << "{\"native_timed_lock_consumers\":3,\"held_timeout\":3,\"unlocked_success\":3}\n";
}
