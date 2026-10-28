// Candidate-only scalar boundary plans; the pinned native prefix runs valid settings only.
#define SWR_PORTS_FLAGS_NO_MAIN
#include "flags.cc"
#ifdef PORTS_DRIVER
int main() {
    static_assert(sizeof(SwrPortsPacketSetting)==16&&offsetof(SwrPortsPacketSetting,copy_len)==8,"packet plan ABI");
    size_t cases=flag_checks(true);
    for(size_t length:{size_t(0),size_t(1),size_t(SW_DATA_EOF_MAXLEN),size_t(SW_DATA_EOF_MAXLEN+1),SIZE_MAX}) {
        auto packet=swr_v1_ports_packet_eof(length,SW_DATA_EOF_MAXLEN);
        assert(packet.value==static_cast<uint8_t>(length));
        assert(packet.copy_len<=SW_DATA_EOF_MAXLEN);
        assert(packet.status==0 ? packet.copy_len==length&&length>0 : packet.copy_len==0);
        if(length==0)assert(packet.status==1);
        if(length>0&&length<=SW_DATA_EOF_MAXLEN)assert(packet.status==0);
        cases++;
    }
    // Wide facts exercise only the new pointer-free classifier, never native copy.
    for(unsigned n=0;n<4096;n++) {
        size_t length=(uint64_t(random_word())<<32)|random_word();
        auto packet=swr_v1_ports_packet_eof(length,SW_DATA_EOF_MAXLEN);
        assert(packet.copy_len<=SW_DATA_EOF_MAXLEN);
        assert(packet.status!=0 || (length>0&&length<=SW_DATA_EOF_MAXLEN));
        assert(packet.status==0 ? packet.copy_len==length : packet.copy_len==0);cases++;
    }
    for(int32_t width:{0,1,2,4,8}) {
        auto packet=swr_v1_ports_packet_width(width);
        assert(packet.value==uint32_t(width)&&packet.status==uint32_t(width==0)&&packet.copy_len==0);cases++;
    }
    for(uint32_t limit:{uint32_t(SW_IPC_BUFFER_SIZE),uint32_t(UINT16_MAX)})
        for(int64_t value:{INT64_MIN,int64_t(-1),int64_t(0),int64_t(1),int64_t(limit),int64_t(limit)+1,INT64_MAX}) {
            auto packet=swr_v1_ports_packet_offset(value,limit);
            auto expected=SW_MAX(0,SW_MIN(value,UINT16_MAX));
            assert(packet.value==expected&&packet.status==uint32_t(expected>limit)&&packet.copy_len==0);cases++;
        }
    printf("%zu normal prefix/flag/buffer and candidate-only packet plan comparisons passed\n",cases);
    return 0;
}
#endif
