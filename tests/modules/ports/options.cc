#define SWR_PORTS_FLAGS_NO_MAIN
#include "flags.cc"
int main() {
    static_assert(sizeof(SwrPortsOption)==56&&offsetof(SwrPortsOption,action)==32&&offsetof(SwrPortsOption,reserved)==52,"option C ABI");
    size_t cases=flag_checks(true);
    unsigned count=0,always=0,defaults=0,aliases=0;
    for(size_t index=0;index<64;index++) {
        auto option=swr_v1_ports_option(index);
        assert(option.reserved==0);
        if(option.action==SWR_PORTS_OPTION_END) {
            assert(index>=31&&option.key.data==nullptr&&option.key.len==0&&option.alias.data==nullptr&&option.alias.len==0);
            assert(option.target==0&&option.converter==0&&option.number_kind==0&&option.policy==0);cases++;continue;
        }
        count++;assert(index<31&&option.key.data&&option.alias.data);
        assert(option.key.data[option.key.len]==0&&option.alias.data[option.alias.len]==0);
        assert(option.action>=SWR_PORTS_OPTION_NUMBER&&option.action<=SWR_PORTS_OPTION_SPECIAL);
        assert(option.converter<=SWR_PORTS_CONVERT_TRUTH&&option.policy<=SWR_PORTS_OPTION_ALWAYS);
        if(option.policy==SWR_PORTS_OPTION_ALWAYS){assert(option.key.len==0&&option.target==SWR_PORTS_SPECIAL_WEBSOCKET_OPTIONS);always++;}
        if(option.policy==SWR_PORTS_MISSING_DEFAULT){assert(option.action==SWR_PORTS_OPTION_FLAG&&option.target==SWR_PORTS_SET_NODELAY);defaults++;}
        if(option.alias.len){assert(option.action==SWR_PORTS_OPTION_SPECIAL&&option.target==SWR_PORTS_SPECIAL_BODY_OFFSET);assert(std::string((const char *)option.alias.data,option.alias.len)=="package_body_start");aliases++;}
        if(option.action==SWR_PORTS_OPTION_FLAG)assert(option.target>=SWR_PORTS_SET_NODELAY&&option.target<=SWR_PORTS_SET_CHECK_LENGTH);
        if(option.action==SWR_PORTS_OPTION_NUMBER||option.action==SWR_PORTS_OPTION_BUFFER)assert(option.target>=SWR_PORTS_NUMBER_BACKLOG&&option.target<=SWR_PORTS_NUMBER_MAX_LENGTH);
        cases++;
    }
    assert(count==31&&always==1&&defaults==1&&aliases==1);
    auto end=swr_v1_ports_option(SIZE_MAX);assert(end.action==0&&end.key.data==nullptr);cases++;
    printf("%zu normal binary-prefix and option catalog ABI comparisons passed\n",cases);
    return 0;
}
