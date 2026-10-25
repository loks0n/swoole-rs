// Ordinary metadata model only. Parser/IO/runtime/lifetime profiles are excluded.
int main() {
    using model::RequestV2;
    using model::String;
    size_t checks=0;
    auto check=[&](bool value) { ++checks; if(!value) throw std::logic_error("RequestV2 ordinary metadata assertion "+std::to_string(checks)); };
    auto same=[&](const upstream_model::Request &old,const RequestV2 &now) {
        check(old.method==now.method());
        check(old.url_offset_==now.url_offset() && old.url_length_==now.url_length());
        check(old.header_length_==now.header_length() && old.max_length_==now.max_length());
        check(old.content_length_==now.content_length());
        check(bool(old.form_data_)==now.has_form());
        check(bool(old.excepted)==now.excepted() && bool(old.too_large)==now.too_large());
        check(bool(old.unavailable)==now.unavailable() && bool(old.header_parsed)==now.header_parsed());
        check(bool(old.tried_to_dispatch)==now.tried_to_dispatch());
        check(bool(old.multipart_header_parsed)==now.multipart_header_parsed());
        check(bool(old.known_length)==now.known_length() && bool(old.keep_alive)==now.keep_alive());
        check(bool(old.chunked)==now.chunked() && bool(old.nobody_chunked)==now.nobody_chunked());
        check(old.buffer_->storage==now.buffer()->storage && old.buffer_->offset==now.buffer()->offset);
    };
    for (const auto &input:std::vector<std::pair<std::string,uint8_t>>{
        {"GET /ordinary HTTP/1.1\r\nHost: example.test\r\nConnection: keep-alive\r\n\r\n",2},
        {"HEAD /ordinary HTTP/1.1\r\nHost: example.test\r\nConnection: keep-alive\r\n\r\n",3},
        {"POST /ordinary HTTP/1.1\r\nHost: example.test\r\nContent-Length: 5\r\n\r\nhello",4}}) {
        String buffer(input.first),original_buffer(input.first);
        upstream_model::Request original; original.buffer_=&original_buffer;
        RequestV2 request;
        request.set_buffer(&buffer);
        check(request.buffer()==&buffer); same(original,request);
        check(original.get_protocol()==0);
        check(request.get_protocol()==0); same(original,request);
        check(request.method()==input.second);
        check(request.url_length()==9);
        check(original.get_header_length()==0);
        check(request.get_header_length()==0); same(original,request);
        check(!request.header_parsed());
        original.parse_header_info();
        request.parse_header_info(); same(original,request);
        check(request.header_parsed());
        check(original.get_header("Host")==request.get_header("Host"));
        check(original.has_expect_header()==request.has_expect_header());
        check(request.get_header("Host")=="example.test");
        check(!request.has_form());
        check(!request.excepted());
        check(!request.has_expect_header());
        original.max_length_=4096; request.set_max_length(4096); same(original,request);
        check(request.max_length()==4096);
        const auto before=request.header_length();
        original.header_length_+=5; request.advance_header_length(5); same(original,request);
        check(request.header_length()==before+5);
        original.tried_to_dispatch=1; request.mark_dispatched(); check(request.tried_to_dispatch()); same(original,request);
        original.clean(); request.clean(); same(original,request);
        check(request.buffer()==&buffer);
        check(request.method()==0 && request.header_length()==0 && request.max_length()==0);
        check(!request.tried_to_dispatch());
        // The borrowed String remains live/unchanged through an ordinary clean.
        check(buffer.storage==input.first);
    }
    {
        String buffer("POST /ordinary HTTP/1.1\r\nContent-Type: multipart/form-data; boundary=ordinary\r\nContent-Length: 20\r\n\r\n");
        String original_buffer(buffer.storage);
        upstream_model::Request original; original.buffer_=&original_buffer;
        RequestV2 request; request.set_buffer(&buffer); same(original,request);
        check(original.get_protocol()==0);
        check(request.get_protocol()==0); same(original,request);
        check(original.get_header_length()==0);
        check(request.get_header_length()==0); same(original,request);
        original.parse_header_info(); request.parse_header_info(); check(request.has_form()); same(original,request);
        original.clean(); request.clean(); check(request.has_form()); check(request.buffer()==&buffer); same(original,request);
        delete original.form_data_; original.form_data_=nullptr;
        request.discard_form(); check(!request.has_form()); same(original,request);
        // No parser, upload, owned body, file or active-resource teardown entered.
    }
    std::cout<<"{\"ordinary_metadata_checks\":"<<checks<<",\"original_metadata_compared\":true,\"parser_io_executed\":false,\"full_gate_passed\":false}"<<std::endl;
}
