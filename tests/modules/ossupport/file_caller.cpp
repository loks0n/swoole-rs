// SPDX-License-Identifier: Apache-2.0
#include "swoole_file.h"
#include <cassert>
#include <cstring>
#include <unistd.h>
#include <fcntl.h>
#include <cstdio>
int main() {
    swoole_init();
    char path[]="/tmp/swoole-rs-m20-XXXXXX";
    int fd=mkstemp(path);assert(fd>=0);unlink(path);
    assert(::write(fd,"abcdef\nhi\0jk",12)==12);
    assert(::lseek(fd,0,SEEK_SET)==0);
    {
        swoole::File f(fd);char buf[16];
        assert(f.read_line(buf,4)==3 && memcmp(buf,"abc\0",4)==0);
        assert(f.get_offset()==4); // Pinned full-chunk behavior deliberately skips 'd'.
        assert(f.read_line(buf,sizeof(buf))==3 && memcmp(buf,"ef\n\0",4)==0);
        assert(f.get_offset()==7);
        assert(f.read_line(buf,sizeof(buf))==3 && memcmp(buf,"hi\0\0",4)==0);
        assert(f.get_offset()==10);
        assert(f.read_line(buf,sizeof(buf))==2 && memcmp(buf,"jk\0",3)==0);
        assert(f.get_offset()==13);
        assert(f.read_line(buf,sizeof(buf))==0);
        assert(f.set_offset(8)==8);
        assert(f.read_all(buf,6)==6 && memcmp(buf,"abcdef",6)==0);
        assert(f.get_offset()==8); // pread ignores and preserves current position.
        assert(f.write_all("XY",2)==2);
        assert(f.get_offset()==8);
        assert(::pread(fd,buf,4,0)==4 && memcmp(buf,"XYcd",4)==0);
        assert(f.close());assert(!f.close());
    }
    swoole_clean();
    puts("actual File read_line/NUL/skip/pread/pwrite/close caller passed");
}
