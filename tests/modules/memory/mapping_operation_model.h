#pragma once
// Inert success effects only. These names live in model:: and never replace
// libc symbols; no Swoole/OS mapping, File, protection or unmap is executed.
#include "swoole_rs_memory.h"
#include <sys/mman.h>
#include <sys/types.h>
#include <fcntl.h>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef SWR_MODEL_FILE_BACKEND
#undef MAP_ANONYMOUS
#undef MAP_ANON
#endif
namespace model {
struct Event { unsigned action; size_t size; int flags, descriptor; };
extern std::vector<Event> events;
extern std::array<std::array<uint64_t,128>,2> storage;
extern std::array<size_t,2> lengths;
extern std::array<bool,2> active;
extern int file_descriptor;
void reset();
void *mmap(void *,size_t,int,int,int,off_t);
int munmap(void *,size_t);
int mprotect(void *,size_t,int);
class File {
    int descriptor_;
  public:
    File(const std::string &path,int flags):descriptor_(file_descriptor) {
        assert(path=="/dev/zero" && flags==O_RDWR);
        events.push_back({1,0,flags,descriptor_});
    }
    ~File(){events.push_back({2,0,0,descriptor_});}
    bool ready()const{return true;}
    int get_fd()const{return descriptor_;}
};
inline void unexpected_warning(){throw std::runtime_error("Normal-only model reached a warning");}
void *sw_shm_malloc(size_t);
void *sw_shm_calloc(size_t,size_t);
int sw_shm_protect(void *,int);
void sw_shm_free(void *);
void *sw_shm_realloc(void *,size_t);
}
#define swoole_sys_warning(...) ::model::unexpected_warning()
