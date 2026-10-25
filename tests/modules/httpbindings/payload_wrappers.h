// Included inside each extracted implementation namespace.
struct HttpContext: ContextData {
 void set_compression_method(const char*,size_t);
 const char*get_content_encoding()const;
};
static void setup(HttpContext&ctx,const Input&in){
 ctx.recv_chunked=in.flags&1;ctx.parse_body=in.flags&2;ctx.request.post_form_urlencoded=in.flags&4;ctx.completed=in.flags&8;
 if(in.flags&16){ctx.request.chunked_body=new NativeString(0);ctx.request.chunked_body->storage=in.prior;ctx.request.chunked_body->sync();}
 if(in.flags&32)ctx.mt_parser=&ctx;
 if(in.flags&64)ctx.form_data_buffer=new NativeString(0);
 ctx.request.body_length=in.previous;ctx.parse_result=in.parse_result;
}
static Result capture(HttpContext&ctx,Result r){
 r.body=ctx.request.chunked_body?ctx.request.chunked_body->storage:"";r.post=ctx.request.post.text;r.length=ctx.request.body_length;
 r.flags=ctx.completed|(ctx.request.chunked_body?2u:0u)|(ctx.mt_parser?4u:0u)|(ctx.form_data_buffer?8u:0u);
 r.trace=oracle->trace;return r;
}
