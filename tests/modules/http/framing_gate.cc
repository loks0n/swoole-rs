#include "framing_oracle.h"
#include <iostream>
#include <vector>
void run_original_frames();
void check(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
int main() {
    try {
        run_original_frames();
        unsigned cases = 0;
        auto compare = [&](const std::string &input, size_t offset, unsigned operation, bool seeded) {
            upstream_frame::Buffer a{const_cast<char *>(input.data()), input.size(), off_t(offset)};
            candidate_frame::Buffer b{const_cast<char *>(input.data()), input.size(), off_t(offset)};
            upstream_frame::Request before; candidate_frame::Request after; before.buffer_ = &a; after.buffer_ = &b;
            if (seeded) {
                before.method = after.method = 19; before.version = after.version = 3;
                before.known_length = after.known_length = 1; before.content_length_ = after.content_length_ = 123;
                before.url_offset_ = after.url_offset_ = 3; before.url_length_ = after.url_length_ = 7;
                before.request_line_length_ = after.request_line_length_ = 9;
            }
            if (operation == 2) before.header_length_ = after.header_length_ = offset;
            auto invoke = [operation](auto &r) {
                if (operation == 0) return r.get_protocol();
                if (operation == 1) return r.get_header_length();
                return r.get_chunked_body_length();
            };
            auto x = invoke(before), y = invoke(after);
            check(x == y && a.offset == b.offset && before.method == after.method && before.version == after.version && before.excepted == after.excepted && before.known_length == after.known_length && before.content_length_ == after.content_length_ && before.url_offset_ == after.url_offset_ && before.url_length_ == after.url_length_ && before.request_line_length_ == after.request_line_length_ && before.header_length_ == after.header_length_, "framing return/state differential"); ++cases;
        };
        const std::vector<std::string> methods = {"DELETE","GET","HEAD","POST","PUT","PATCH","CONNECT","OPTIONS","TRACE","COPY","LOCK","MKCOL","MOVE","PROPFIND","PROPPATCH","UNLOCK","REPORT","MKACTIVITY","CHECKOUT","MERGE","M-SEARCH","NOTIFY","SUBSCRIBE","UNSUBSCRIBE","PURGE"};
        for (auto &method : methods) for (auto &target : {std::string("/"),std::string("/search?q=x#z"),std::string("/"+std::string(128,'a'))}) {
            for (const char *version : {"HTTP/1.0", "HTTP/1.1", "HTTP/1.2", "HTTP/2.0"}) for (bool seeded : {false,true}) {
                for (const char *spaces : {" ", "    "}) compare(method+spaces+target+spaces+version+"\r\n",0,0,seeded);
            }
        }
        compare("UNSUBSCRIBE /index.html\r\n",0,0,false);
        const std::vector<std::string> requests = {"GET / HTTP/1.1\r\n", "POST / HTTP/1.0\r\n", "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n", "GET/target HTTP/1.1\r\n", "UNKNOWN / HTTP/1.1\r\n", "get / HTTP/1.1\r\n", "GET \n HTTP/1.1\r\n", std::string("GET /\0 HTTP/1.1\r\n",17)};
        // Short-target incremental prefixes reach the version before the old
        // end()+8 bug. Long-target fallthroughs are candidate-only below.
        for (auto &request : requests) for (size_t n = 0; n <= request.size(); ++n) for (bool seeded : {false,true}) compare(request.substr(0,n),0,0,seeded);
        const std::vector<std::string> headers = {"GET / HTTP/1.1\r\nHost: example\r\n\r\n", "GET / HTTP/1.1\r\nX: \t\r\nHost:value\r\n\r\nbody", "GET / HTTP/1.1\r\nExpect: 100-continue\r\n\r\n", "x\rxExpect: 100-continue", "GET / HTTP/1.1\r\nExpect: nope\r\nExpect: 100-continue\r\n\r\n", "GET / HTTP/1.1\r\n Host: value\r\nHost: other\r\n\r\n", "GET / HTTP/1.1\r\nXHost: bad\r\nHost:\v value\r\n\r\n", "GET / HTTP/1.1\r\nexpect: 100-continue-extra\r\n\r\n", "GET / HTTP/1.1\r\nExpect:100-continue\r\n\r\n", std::string("GET / HTTP/1.1\r\nX: a\0b\r\n\r\n",26)};
        for (auto &header : headers) {
            for (size_t n = 4; n <= header.size(); ++n) for (size_t at = 0; at <= n; ++at) compare(header.substr(0,n),at,1,false);
            for (size_t n = 0; n <= header.size(); ++n) {
                auto part = header.substr(0,n);
                upstream_frame::Buffer a{part.data(),part.size(),0}; candidate_frame::Buffer b{part.data(),part.size(),0};
                upstream_frame::Request before; candidate_frame::Request after; before.buffer_=&a;after.buffer_=&b;
                check(before.has_expect_header()==after.has_expect_header(),"Expect scanner differential"); ++cases;
            }
            if (header.size() >= 16) {
                upstream_frame::Buffer a{const_cast<char *>(header.data()),header.size(),0}; candidate_frame::Buffer b{const_cast<char *>(header.data()),header.size(),0};
                upstream_frame::Request before; candidate_frame::Request after; before.buffer_=&a;after.buffer_=&b;
                before.url_offset_=after.url_offset_=4;before.url_length_=after.url_length_=1;
                auto end=header.find("\r\n\r\n"); if(end==std::string::npos) end=header.size(); else end+=4;
                before.header_length_=after.header_length_=end;
                for (auto name:{"Host","host","X","Expect","Missing",""}) { check(before.get_header(name)==after.get_header(name),"header value differential"); ++cases; }
            }
        }
        const std::vector<std::string> chunks = {"0\r\n\r\n", "3\r\nabc\r\n0\r\n\r\n", "3\r\nabcXX0\r\n\r\n", "1\r\na\r\n2\r\nbc\r\n0\r\n\r\n", "0x0\r\n\r\n", "+0\r\n\r\n", "-0\r\n\r\n", " \t0\r\n\r\n", "q\r\n0\r\n\r\n", "3;x\r\nabc\r\n0\r\n\r\n", "\r\nXYZ0\r\n\r\n"};
        for(auto &chunk:chunks) for(size_t n=0;n<=chunk.size();++n) for(bool seeded:{false,true}) { compare(chunk.substr(0,n),0,2,seeded);compare("hdr"+chunk.substr(0,n),3,2,seeded); }
        uint32_t seed = 3921;
        auto random = [&]() { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed; };
        for (unsigned trial=0;trial<1024;++trial) {
            std::string body; unsigned parts=1+random()%8;
            for(unsigned part=0;part<parts;++part) {
                unsigned length=1+random()%64; char hex[32]; std::snprintf(hex,sizeof(hex),"%x",length);
                body+=hex;body+="\r\n";for(unsigned i=0;i<length;++i) body+=char(random());body+="\r\n";
            }
            body+="0\r\n\r\n";compare(body,0,2,trial%2);
            const std::string header="POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n";
            compare(header+body,header.size(),2,trial%2);
        }
        for (auto &request : {std::string("GET /"+std::string(32,'a')), std::string("GET "+std::string(32,' '))}) {
            candidate_frame::Buffer b{const_cast<char *>(request.data()),request.size(),0}; candidate_frame::Request after;after.buffer_=&b;
            check(after.get_protocol()==SW_ERR && b.offset==0,"corrected partial request-line bounds");
        }
        std::string huge="FFFFFFFFFFFFFFFF\r\nx0\r\n\r\n";candidate_frame::Buffer b{huge.data(),huge.size(),0};candidate_frame::Request after;after.buffer_=&b;
        check(after.get_chunked_body_length()==SW_ERR && !after.known_length,"corrected chunk pointer overflow");
        std::cout << "{\"original_tests_per_engine\":3,\"framing_differential_cases\":"<<cases<<",\"corrected_boundary_cases\":3,\"errors\":0}\n";
    } catch(const std::exception &error) { std::cerr<<error.what()<<'\n';return 1; }
}
