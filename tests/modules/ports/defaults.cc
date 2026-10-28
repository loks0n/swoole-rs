// Exact constructor bodies; native initializers/storage/copy remain in C++.
#ifdef PORTS_DRIVER
#include "swoole_rs_ports.h"
#endif
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <type_traits>
#include "config.inc"
struct Server { uint64_t tag; };
struct Protocol {
    char package_length_type=0;
    uint8_t package_length_size=0;
    uint16_t package_length_offset=0,package_body_offset=0;
    uint32_t package_max_length=0;
    uint8_t package_eof_len=0;
    char package_eof[SW_DATA_EOF_MAXLEN]{};
    void *private_data_2=nullptr;
};
#define PORT_FIELDS uint16_t object_id; Protocol protocol{}; \
    bool open_length_check=false,open_eof_check=false; explicit ListenPort(Server *)
namespace original { struct ListenPort { PORT_FIELDS; }; }
namespace selected { struct ListenPort { PORT_FIELDS; }; }
// Each side's body in its own translation unit; the selected one also holds the driver.
namespace PORTS_SIDE {
#include "body.inc"
}
#ifdef PORTS_DRIVER
int main() {
    static_assert(sizeof(SwrPortsDefaults)==24&&offsetof(SwrPortsDefaults,eof_length)==20,"constructor ABI");
    Server servers[16]{};uint64_t cases=0;
    for(unsigned i=0;i<=16;i++) {
        Server *server=i==16?nullptr:&servers[i];
        original::ListenPort a(server);selected::ListenPort b(server);
        assert(a.object_id==b.object_id&&b.object_id==0);
        assert(a.protocol.package_length_type==b.protocol.package_length_type&&b.protocol.package_length_type=='N');
        assert(a.protocol.package_length_size==b.protocol.package_length_size&&b.protocol.package_length_size==4);
        assert(a.protocol.package_length_offset==b.protocol.package_length_offset&&b.protocol.package_length_offset==0);
        assert(a.protocol.package_body_offset==b.protocol.package_body_offset&&b.protocol.package_body_offset==4);
        assert(a.protocol.package_max_length==b.protocol.package_max_length&&b.protocol.package_max_length==SW_INPUT_BUFFER_SIZE);
        assert(a.protocol.package_eof_len==b.protocol.package_eof_len&&b.protocol.package_eof_len==sizeof(SW_DATA_EOF)-1);
        assert(!memcmp(a.protocol.package_eof,b.protocol.package_eof,sizeof(a.protocol.package_eof)));
        assert(!memcmp(b.protocol.package_eof,SW_DATA_EOF,b.protocol.package_eof_len));
        for(size_t n=b.protocol.package_eof_len;n<sizeof(b.protocol.package_eof);n++)assert(b.protocol.package_eof[n]==0);
        assert(a.protocol.private_data_2==server&&b.protocol.private_data_2==server);
        assert(!a.open_length_check&&!b.open_length_check&&!a.open_eof_check&&!b.open_eof_check);++cases;
    }
    for(uint32_t maximum:{0u,1u,255u,65535u,65536u,0x7fffffffu,0x80000000u,0xffffffffu})
        for(uint32_t length=0;length<=SW_DATA_EOF_MAXLEN;length++) {
            auto value=swr_v1_ports_defaults(maximum,length);
            assert(value.object_id==0&&value.length_type=='N'&&value.length_size==4&&value.body_offset==4);
            assert(value.max_length==maximum&&value.eof_length==length);++cases;
        }
    std::cout<<"constructor-defaults "<<cases<<" exact-body/direct-ABI cases PASS\n";
}
#endif
