#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include <type_traits>
#include <new>
#include <sys/types.h>
#include <sys/uio.h>
#include "swoole_rs_reactor.h"
#define SW_LOOP_N(n) for(decltype(n) i=0;i<n;++i)
namespace swoole {
#include "iov_owned.inc"
}
int main(){using namespace swoole;unsigned cases=0,checks=0;uint64_t metadata=0;auto check=[&](bool value){assert(value);++checks;};
check(std::is_standard_layout<IOVector>::value);
check(swr_v1_reactor_iov_owned_layout(0)==sizeof(swr_v1_reactor_iov_allocation));
check(swr_v1_reactor_iov_owned_layout(1)==alignof(swr_v1_reactor_iov_allocation));
check(swr_v1_reactor_iov_owned_layout(2)==offsetof(swr_v1_reactor_iov_allocation,original));
check(swr_v1_reactor_iov_owned_layout(3)==offsetof(swr_v1_reactor_iov_allocation,iterator));
check(swr_v1_reactor_iov_owned_layout(4)==offsetof(swr_v1_reactor_iov_allocation,status));

check(swr_v1_reactor_iov_progress_layout(0)==sizeof(swr_v1_reactor_iov_progress_reply));check(swr_v1_reactor_iov_progress_layout(1)==alignof(swr_v1_reactor_iov_progress_reply));check(swr_v1_reactor_iov_progress_layout(2)==offsetof(swr_v1_reactor_iov_progress_reply,offset_bytes));check(swr_v1_reactor_iov_progress_layout(3)==offsetof(swr_v1_reactor_iov_progress_reply,advance));check(swr_v1_reactor_iov_progress_layout(4)==offsetof(swr_v1_reactor_iov_progress_reply,consumed));check(swr_v1_reactor_iov_progress_layout(5)==offsetof(swr_v1_reactor_iov_progress_reply,remain_count));check(swr_v1_reactor_iov_progress_layout(6)==offsetof(swr_v1_reactor_iov_progress_reply,index));check(swr_v1_reactor_iov_progress_layout(7)==offsetof(swr_v1_reactor_iov_progress_reply,action));
for(const std::vector<size_t>&lengths:std::vector<std::vector<size_t>>{{1},{2,3},{1,3,7},{4,1,2,9},{0,1,0,3}}){
 size_t total=0;for(auto length:lengths)total+=length;std::string bytes;for(size_t i=0;i<total;++i)bytes+=static_cast<char>(i);std::vector<iovec>input;size_t start=0;for(auto length:lengths){input.push_back({&bytes[0]+start,length});start+=length;}auto snapshot=input;
 auto remainder=[](const IOVector &v){std::string value;auto *iov=v.get_iterator();for(int i=0;i<v.get_remain_count();++i)value.append(static_cast<const char*>(iov[i].iov_base),iov[i].iov_len);return value;};
 auto unchanged=[&](IOVector &v){check(v.length()==total);check(v.count==static_cast<int>(input.size()));for(size_t i=0;i<input.size();++i){check(v.iov[i].iov_base==snapshot[i].iov_base&&v.iov[i].iov_len==snapshot[i].iov_len);check(input[i].iov_base==snapshot[i].iov_base&&input[i].iov_len==snapshot[i].iov_len);}};
 for(size_t sent=1;sent<=total;++sent){IOVector v(input.data(),input.size());auto *initial=v.get_iterator();v.update_iterator(sent);check(v.get_remain_count()==(sent==total?0:static_cast<int>(input.size())-v.get_index()));if(sent==total)check(v.get_iterator()==initial);else{check(remainder(v)==bytes.substr(sent));check(v.get_iterator()==initial+v.get_index());}unchanged(v);metadata+=v.get_offset_bytes()+v.get_index()+v.get_remain_count();++cases;}
 {IOVector v(input.data(),input.size());for(size_t sent=1;sent<=total;++sent){auto *previous=v.get_iterator();v.update_iterator(1);if(sent==total){check(v.get_remain_count()==0);check(v.get_iterator()==previous);}else check(remainder(v)==bytes.substr(sent));unchanged(v);metadata+=v.get_offset_bytes()+v.get_index()+v.get_remain_count();}++cases;}
}
// Complete positive constructor/storage copies, independent input lifetime and
// original descriptor span stability while updating only the iterator copy.
for(int count:{1,3,17,65}) {
 std::string bytes(count*3,'x');std::vector<iovec> input;
 for(int i=0;i<count;++i)input.push_back({&bytes[0]+i*3,3});
 auto before=input;IOVector v(input.data(),count);
 check(v.iov!=input.data());check(v.iov_iterator==v.iov+count);
 check(v.count==count&&v.remain_count==count&&v.index==0&&v.offset_bytes==0);
 check(reinterpret_cast<uintptr_t>(v.iov)%alignof(iovec)==0);
 check(v.length()==size_t(count*3));
 for(int i=0;i<count;++i){check(v.iov[i].iov_base==before[i].iov_base&&v.iov[i].iov_len==3);check(v.iov_iterator[i].iov_base==before[i].iov_base&&v.iov_iterator[i].iov_len==3);}
 v.update_iterator(1);check(v.get_index()==0&&v.get_remain_count()==count&&v.get_offset_bytes()==1);
 check(v.get_iterator()->iov_base==static_cast<char*>(before[0].iov_base)+1&&v.get_iterator()->iov_len==2);
 check(v.length()==size_t(count*3));
 for(int i=0;i<count;++i){check(v.iov[i].iov_base==before[i].iov_base&&v.iov[i].iov_len==3);check(input[i].iov_base==before[i].iov_base&&input[i].iov_len==before[i].iov_len);}
 ++cases;
}
// Preserve actual pinned metadata at an exact boundary after an earlier partial
// update; do not normalize offset_bytes while moving into the next descriptor.
{std::string data="abcde";iovec input[]={{&data[0],2},{&data[2],3}};IOVector v(input,2);v.update_iterator(1);check(v.get_offset_bytes()==1);v.update_iterator(1);check(v.get_index()==1&&v.get_remain_count()==1&&v.get_offset_bytes()==1);check(v.get_iterator()->iov_base==&data[2]&&v.get_iterator()->iov_len==3);++cases;}
std::cout<<"{\"class_size\":"<<sizeof(IOVector)<<",\"class_align\":"<<alignof(IOVector)<<",\"iterator_offset\":"<<offsetof(IOVector,iov_iterator)<<",\"count_offset\":"<<offsetof(IOVector,count)<<",\"remaining_offset\":"<<offsetof(IOVector,remain_count)<<",\"index_offset\":"<<offsetof(IOVector,index)<<",\"offset_bytes_offset\":"<<offsetof(IOVector,offset_bytes)<<",\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"metadata_checksum\":"<<metadata<<",\"layout_facts\":17,\"positive_progress_only\":true}\n";
}
