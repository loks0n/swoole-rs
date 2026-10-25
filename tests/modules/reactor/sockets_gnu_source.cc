// Official GNU source bodies with inert typed metadata helpers only.
// This is NOT an installed libstdc++ or Native Linux registry oracle.
#include "actual-gnu.inc"
#include <iostream>
#include <sstream>
#include <string>
#ifndef SWR_GNU_KEY
#define SWR_GNU_KEY int
#endif
using Key=SWR_GNU_KEY;
static void entries(const std::vector<std::pair<Key,uintptr_t>> &values) {
    if(values.empty()){std::cout<<'-';return;}
    for(const auto &entry:values)std::cout<<entry.first<<':'<<entry.second<<';';
}
int main() {
    std::unique_ptr<GnuSource<Key>> owner;
    std::string line;
    while(std::getline(std::cin,line)) {
        std::istringstream input(line);char op;Key key=0;uintptr_t token=0;input>>op;
        if(op=='n')owner.reset(new GnuSource<Key>);
        else if(op=='p'){input>>key>>token;owner->put(key,token);}
        else if(op=='g'){input>>key;owner->get(key);}
        else if(op=='e'){input>>key;owner->erase(key);}
        else if(op=='c')owner->clear();
        else return 2;
        if(input.fail())return 3;
        GnuSource<Key> copied(*owner);
        std::cout<<op<<'\t'<<key<<'\t'<<token<<'\t'<<owner->size()<<'\t'<<owner->buckets()<<'\t'<<owner->threshold()<<'\t';
        entries(owner->values());std::cout<<'\t';entries(copied.values());std::cout<<'\n';
    }
}
