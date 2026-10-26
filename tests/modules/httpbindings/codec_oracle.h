#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#ifndef CODEC_CAPABILITIES
#define CODEC_CAPABILITIES 7
#endif
#if CODEC_CAPABILITIES
#define SW_HAVE_COMPRESSION 1
#endif
#if CODEC_CAPABILITIES & 1
#define SW_HAVE_ZLIB 1
#endif
#if CODEC_CAPABILITIES & 2
#define SW_HAVE_BROTLI 1
#endif
#if CODEC_CAPABILITIES & 4
#define SW_HAVE_ZSTD 1
#endif
#define BROTLI_MIN_QUALITY 0
#define BROTLI_MAX_QUALITY 11
#define BROTLI_DEFAULT_WINDOW 22
#define BROTLI_DEFAULT_MODE 0
#define BROTLI_TRUE 1
#define Z_NO_COMPRESSION 0
#define Z_DEFAULT_COMPRESSION -1
#define Z_BEST_SPEED 1
#define Z_BEST_COMPRESSION 9
#define Z_OK 0
#define Z_STREAM_END 1
#define Z_DEFLATED 8
#define SW_ZLIB_DEF_MEM_LEVEL 8
#define SW_ZLIB_ENCODING_DEFLATE 0x0f
#define Z_DEFAULT_STRATEGY 0
#define Z_FINISH 4
enum {HTTP_COMPRESS_NONE,HTTP_COMPRESS_GZIP,HTTP_COMPRESS_DEFLATE,HTTP_COMPRESS_BR,HTTP_COMPRESS_ZSTD};
struct Exit {};
struct Oracle {std::vector<std::string>trace;unsigned config=0;size_t fail=SIZE_MAX;std::function<void(const std::string&)>hook;
 void event(const std::string&s){trace.push_back(s);if(trace.size()-1==fail)throw Exit{};if(hook)hook(s);}};
extern thread_local Oracle *oracle;
struct String {
 std::vector<unsigned char>storage;char*str;size_t size,length=0,offset=0;
 explicit String(size_t n){oracle->event("new:"+std::to_string(n));storage.resize(n);str=reinterpret_cast<char*>(storage.data());size=n;}
};
inline void fill(unsigned char*out,size_t capacity,bool failed){size_t n=std::min(capacity,failed?size_t(3):size_t(7));std::fill_n(out,n,0xa5);}
inline size_t BrotliEncoderMaxCompressedSize(size_t n){oracle->event("brotli-bound:"+std::to_string(n));return n+64;}
inline int BrotliEncoderCompress(int level,int window,int mode,size_t n,const uint8_t*,size_t*capacity,uint8_t*out){
 oracle->event("brotli:"+std::to_string(level)+":"+std::to_string(n)+":"+std::to_string(*capacity));bool failed=oracle->config&8;fill(out,*capacity,failed);*capacity=failed?3:7;return !failed;
}
inline int ZSTD_maxCLevel(){oracle->event("zstd-max");return 22;}
inline int ZSTD_minCLevel(){oracle->event("zstd-min");return -5;}
inline size_t ZSTD_compressBound(size_t n){oracle->event("zstd-bound:"+std::to_string(n));return n+32;}
inline size_t ZSTD_compress(void*out,size_t capacity,const void*,size_t n,int level){oracle->event("zstd:"+std::to_string(level)+":"+std::to_string(n)+":"+std::to_string(capacity));bool failed=oracle->config&8;fill(static_cast<unsigned char*>(out),capacity,failed);return failed?SIZE_MAX:size_t(7);}
inline bool ZSTD_isError(size_t n){oracle->event("zstd-error");return n==SIZE_MAX;}
inline const char*ZSTD_getErrorName(size_t){oracle->event("zstd-error-name");return "fixture-error";}
using Bytef=unsigned char;using uInt=unsigned;using voidpf=void*;
inline voidpf php_zlib_alloc(voidpf,uInt,uInt){oracle->event("zlib-allocator");return nullptr;}
inline void php_zlib_free(voidpf,voidpf){oracle->event("zlib-free");}
struct z_stream {voidpf(*zalloc)(voidpf,uInt,uInt)=nullptr;void(*zfree)(voidpf,voidpf)=nullptr;Bytef*next_in=nullptr;size_t avail_in=0;Bytef*next_out=nullptr;size_t avail_out=0;size_t total_out=0;};
inline int deflateInit2(z_stream*z,int level,int,int encoding,int,int){oracle->event("zlib-init:"+std::to_string(level)+":"+std::to_string(encoding));z->zalloc(nullptr,1,1);return oracle->config&16?-2:Z_OK;}
inline int deflate(z_stream*z,int){oracle->event("zlib-deflate:"+std::to_string(z->avail_in)+":"+std::to_string(z->avail_out));bool failed=oracle->config&32;fill(z->next_out,z->avail_out,failed);z->total_out=failed?3:7;return failed?-5:Z_STREAM_END;}
inline int deflateEnd(z_stream*z){oracle->event("zlib-end");z->zfree(nullptr,nullptr);return Z_OK;}
inline void swoole_warning(const char*format,...){char text[512];va_list args;va_start(args,format);vsnprintf(text,sizeof(text),format,args);va_end(args);oracle->event("warning:"+std::string(text));}
struct Result {std::vector<std::string>trace;std::vector<unsigned char>buffer;size_t size=0,length=0,offset=0;int level=0;bool compressed=false,success=false,exited=false;
 bool operator==(const Result&r)const{return trace==r.trace&&buffer==r.buffer&&size==r.size&&length==r.length&&offset==r.offset&&level==r.level&&compressed==r.compressed&&success==r.success&&exited==r.exited;}};
#define CODEC_DECL(N) namespace N {Result run(int,int,unsigned,size_t);}
CODEC_DECL(upstream_codec)
CODEC_DECL(candidate_codec)
