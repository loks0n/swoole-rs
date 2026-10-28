// Complete original/selected setter bodies. No IO, callbacks or fault injection.
#ifdef PORTS_DRIVER
#include "swoole_rs_ports.h"
#endif
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <string>
#include <type_traits>

struct Protocol {
    static int default_length_func() { return 42; }
    static int sentinel_length() { return 17; }
    int (*get_package_length)()=sentinel_length;
    bool split_by_eof=false;
    uint8_t package_eof_len=0;
    char package_eof[8]{'x','x','x','x','x','x','x','x'};
    char package_length_type='N';
    uint8_t package_length_size=4;
    uint16_t package_length_offset=123,package_body_offset=456;
};
#define PORT_FIELDS \
    Protocol protocol; bool open_eof_check=false,open_length_check=false; \
    void set_eof_protocol(const std::string &,bool); \
    void set_length_protocol(uint32_t,char,uint32_t); void set_stream_protocol()
namespace original { struct ListenPort { PORT_FIELDS; }; }
namespace selected { struct ListenPort { PORT_FIELDS; }; }
// Each side's body in its own translation unit; the selected one also holds the driver.
namespace PORTS_SIDE {
#include "type-size.inc"
namespace network { struct Stream { static void set_protocol(Protocol *); };
#include "stream.inc"
}
#include "body.inc"
}
#ifdef PORTS_DRIVER
static void equal(const original::ListenPort &a,const selected::ListenPort &b) {
    assert(a.protocol.get_package_length==b.protocol.get_package_length);
    assert(a.open_eof_check==b.open_eof_check&&a.open_length_check==b.open_length_check);
    assert(a.protocol.split_by_eof==b.protocol.split_by_eof);
    assert(a.protocol.package_eof_len==b.protocol.package_eof_len);
    assert(!memcmp(a.protocol.package_eof,b.protocol.package_eof,sizeof(a.protocol.package_eof)));
    assert(a.protocol.package_length_type==b.protocol.package_length_type);
    assert(a.protocol.package_length_size==b.protocol.package_length_size);
    assert(a.protocol.package_length_offset==b.protocol.package_length_offset);
    assert(a.protocol.package_body_offset==b.protocol.package_body_offset);
}
int main() {
    static_assert(sizeof(SwrPortsFramingInput)==40&&sizeof(SwrPortsFramingSettings)==32,"framing ABI");
    static_assert(offsetof(SwrPortsFramingInput,length)==8&&offsetof(SwrPortsFramingSettings,enabled)==8,"framing offsets");
    uint64_t cases=0;
    original::ListenPort a;selected::ListenPort b;
    for(size_t length:{0u,1u,2u,7u,8u,9u,16u,1024u})for(bool right:{false,true}) {
        std::string value(length,'x');for(size_t i=0;i<length;i++)value[i]=char(i);
        a.set_eof_protocol(value,right);b.set_eof_protocol(value,right);equal(a,b);
        auto plan=swr_v1_ports_framing_settings({SWR_PORTS_EOF_SETTINGS,right,length,8,0,0,0,0});
        assert(plan.enabled==1&&plan.split==!right&&plan.length==std::min(length,size_t(8)));
        assert(plan.length_type==0&&plan.length_size==0&&plan.length_offset==0&&plan.body_offset==0);++cases;
    }
    for(unsigned type=0;type<256;type++)
        for(uint32_t offset:{0u,1u,255u,65535u,65536u,65537u,0x80000000u,0xffffffffu})
            for(uint32_t body:{0u,1u,255u,65535u,65536u,65537u,0x80000000u,0xffffffffu}) {
                a.set_length_protocol(offset,char(type),body);b.set_length_protocol(offset,char(type),body);equal(a,b);++cases;
            }
    auto maximum=swr_v1_ports_framing_settings({SWR_PORTS_EOF_SETTINGS,0,SIZE_MAX,8,0,0,0,0});
    assert(maximum.length==8&&maximum.split==1);++cases;
    auto absent=swr_v1_ports_framing_settings({UINT32_MAX,0,0,0,0,0,0,0});
    assert(!absent.length&&!absent.enabled&&!absent.split&&!absent.length_type&&!absent.length_size&&!absent.length_offset&&!absent.body_offset);++cases;
    for(unsigned iteration=0;iteration<256;iteration++) {
        a.protocol.get_package_length=Protocol::sentinel_length;b.protocol.get_package_length=Protocol::sentinel_length;
        a.set_length_protocol(iteration*257,char(iteration),UINT32_MAX-iteration);
        b.set_length_protocol(iteration*257,char(iteration),UINT32_MAX-iteration);
        a.set_eof_protocol(std::string(iteration%17,char(iteration)),iteration%2);
        b.set_eof_protocol(std::string(iteration%17,char(iteration)),iteration%2);
        a.set_stream_protocol();b.set_stream_protocol();equal(a,b);
        assert(b.open_length_check&&b.protocol.get_package_length==Protocol::default_length_func);
        assert(b.protocol.package_length_type=='N'&&b.protocol.package_length_size==4);
        assert(b.protocol.package_length_offset==0&&b.protocol.package_body_offset==4);
        ++cases;
    }
    auto stream=swr_v1_ports_stream_settings();
    assert(stream.enabled==1&&stream.length_type=='N'&&stream.length_size==4&&stream.body_offset==4);
    assert(!stream.length&&!stream.split&&!stream.length_offset);++cases;
    std::cout<<"framing-settings "<<cases<<" exact-body and direct-ABI cases PASS\n";
}
#endif
