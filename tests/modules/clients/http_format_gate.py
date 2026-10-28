#!/usr/bin/env python3
"""Actual native request formatter callers and supplemental bounded-capacity codec comparisons.

No allocation, IO, Zend or whole request-runtime parity claim. Native positive
printf capacities are restricted to INT_MAX; required initialized spans are real.
"""
import argparse,json,sys
from pathlib import Path
import gate
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import hybrid_tree
def between(text,start,end,after=0):
 i=text.index(start,after);return text[i:text.index(end,i)]
def pinned_defines(config):
 defines_list=[];lines=config.splitlines()
 for i,line in enumerate(lines):
  if any(line.startswith('#define '+name+' ') for name in ['SW_HTTP_CLIENT_BOUNDARY_TOTAL_SIZE','SW_HTTP_FORM_RAW_DATA_FMT','SW_HTTP_FORM_FILE_DATA_FMT']):
   define=line
   while define.endswith('\\'):
    i+=1;define+='\n'+lines[i]
   defines_list.append(define)
 return '\n'.join(defines_list)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True,help='Rust archive of the hybrid build under test');p.add_argument('--output',type=Path,required=True);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-sanitized',action='store_true');a=p.parse_args()
 if a.rust_sanitized and not a.sanitize:p.error('--rust-sanitized requires --sanitize')
 out=a.output.parent/(a.output.stem+'-artifacts');out.mkdir(parents=True,exist_ok=True);gate.LOG=out/'commands';gate.LOG.mkdir(exist_ok=True)
 # Native side from the pin, Rust side from the hybrid build's fully patched tree.
 hybrid_source,hybrid_flags=hybrid_tree(a.archive)
 trees={'native':lambda path:gate.run(['git','-C',a.source,'show',f'{gate.PIN}:{path}']),'rust':lambda path:(hybrid_source/path).read_text()}
 destination='ext-src/swoole_http_client_coro.cc';original=trees['native'](destination);selected=trees['rust'](destination)
 helpers=gate.body(selected,'static swr_v1_clients_format_span clients_format_span(const char *data, size_t length) {')+'\n'+gate.body(selected,'static size_t clients_format_request(uint32_t kind, swr_v1_clients_format_span first,')
 signature='static void add_content_length(String *buf, size_t length) {'
 def snippets(text,new):
  return dict(content=gate.body(text,signature),proxy=between(text,'        proxy_uri_len = clients_format_request(' if new else "        if (nullptr == memchr(_host, ':', _host_len))",'        buffer->append(proxy_uri, proxy_uri_len);'),type=between(text,'        ssize_t n = clients_format_request(2' if new else '        ssize_t n = sw_snprintf(header_buf,','        buffer->append(header_buf, n);'),raw=between(text,'                n = clients_format_request(3' if new else '                n = sw_snprintf(header_buf,','                buffer->append(header_buf, n);',text.index('// ============ form-data body')),file=between(text,'                n = clients_format_request(4' if new else '                n = sw_snprintf(header_buf,','                /**',text.index(' * part header')),end=between(text,'        n = clients_format_request(5' if new else '        n = sw_snprintf(header_buf, sizeof(header_buf), "--%.*s--','        if (socket->send_all(header_buf, n) != n)'))
 before=snippets(original,False);after=snippets(selected,True)
 for key in before:
  if before[key]==after[key] or 'clients_format_request' not in after[key]:raise ValueError('Missing actual Rust formatter caller '+key)
 template=Path(__file__).with_name('http_format_witness.cpp');prelude,rest=template.read_text().split('// DECLARATIONS');facade,rest=rest.split('// ENTRY');entry=rest.split('// DRIVER')[0]
 native_bounded=r'''switch(kind){case 0:return sw_snprintf(output,capacity,"Content-Length: %zu\r\n\r\n",number);case 1:if(std::memchr(a.data(),':',a.size()))return sw_snprintf(output,capacity,"%s%s%s","http://",a.c_str(),b.c_str());else return sw_snprintf(output,capacity,"%s%s:%u%s","http://",a.c_str(),static_cast<unsigned>(number),b.c_str());case 2:return sw_snprintf(output,capacity,"Content-Type: multipart/form-data; boundary=%.*s\r\n",static_cast<int>(a.size()),a.c_str());case 3:return sw_snprintf(output,capacity,SW_HTTP_FORM_RAW_DATA_FMT,static_cast<int>(a.size()),a.c_str(),static_cast<int>(b.size()),b.c_str());case 4:return sw_snprintf(output,capacity,SW_HTTP_FORM_FILE_DATA_FMT,static_cast<int>(a.size()),a.c_str(),static_cast<int>(b.size()),b.c_str(),static_cast<int>(c.size()),c.c_str(),static_cast<int>(d.size()),d.c_str());case 5:return sw_snprintf(output,capacity,"--%.*s--\r\n",static_cast<int>(a.size()),a.c_str());}return 0;'''
 rust_bounded='return clients_format_request(kind, clients_format_span(a.data(),a.size()), clients_format_span(b.data(),b.size()), clients_format_span(c.data(),c.size()), clients_format_span(d.data(),d.size()),number,output,capacity);'
 def block(name,parts):
  read=trees[name];rust=name=='rust'
  printf=gate.body(read('src/core/base.cc'),'size_t sw_snprintf(char *buf, size_t size, const char *format, ...) {')
  text=facade.replace('BODY_NAMESPACE',name).replace('// NATIVE_PRINTF',printf).replace('// FORMAT_HELPERS',helpers if rust else '').replace('// CONTENT_LENGTH',parts['content']).replace('// PROXY',parts['proxy']).replace('// MULTIPART_TYPE',parts['type']).replace('// MULTIPART_RAW',parts['raw']).replace('// MULTIPART_FILE',parts['file']).replace('// MULTIPART_END',parts['end']).replace('// BOUNDED_FORMAT',rust_bounded if rust else native_bounded)
  return ('#include "swoole_rs_clients.h"\n' if rust else '')+prelude.replace('// PINNED_DEFINES',pinned_defines(read('include/swoole_config.h')))+text
 driver=r'''int main(){size_t caller_cases=0,bounded_cases=0;std::vector<size_t> lengths={0,1,7,38,39,40,100,2040,2048,2050};std::vector<size_t> numbers={0,1,9,10,99,100,65535,std::numeric_limits<size_t>::max()};
 for(auto n:numbers){native::String x;rust::String y;errno=17;native::content_length(&x,n);int e=errno;errno=17;rust::content_length(&y,n);if(x.data!=y.data||errno!=e)return 1;++caller_cases;}
 for(unsigned byte=0;byte<256;++byte)for(size_t length:lengths){std::string a(39,'b'),b(length,static_cast<char>(byte)),c(length,'f'),d(length,'t');a[byte%39]=static_cast<char>(byte);if(length>1){b[length/2]=0;c[length/2]=0;}if(length>2)b[length-1]=':';for(unsigned kind=1;kind<6;++kind){char x[8192],y[8192];std::memset(x,0x5a,sizeof(x));std::memset(y,0x5a,sizeof(y));errno=17;size_t xn=kind==1?native::proxy(b,c,byte*257,x):native::multipart(kind,a,b,c,d,*reinterpret_cast<char(*)[2048]>(x));int xe=errno;errno=17;size_t yn=kind==1?rust::proxy(b,c,byte*257,y):rust::multipart(kind,a,b,c,d,*reinterpret_cast<char(*)[2048]>(y));if(xn!=yn||xe!=errno||std::memcmp(x,y,sizeof(x))){std::cerr<<"caller "<<kind<<":"<<byte<<":"<<length<<":"<<xn<<":"<<yn<<"\n";return 1;}++caller_cases;}
 for(unsigned kind=0;kind<6;++kind)for(size_t capacity:{0,1,2,7,15,16,19,20,21,22,23,39,40,64,2048}){char x[4096],y[4096];std::memset(x,0x5a,sizeof(x));std::memset(y,0x5a,sizeof(y));size_t number=kind==1?byte*257:numbers[byte%numbers.size()];errno=17;auto xn=native::bounded(kind,a,b,c,d,number,x,capacity);int xe=errno;errno=17;auto yn=rust::bounded(kind,a,b,c,d,number,y,capacity);if(xn!=yn||xe!=errno||std::memcmp(x,y,sizeof(x))){std::cerr<<"bounded "<<kind<<":"<<byte<<":"<<length<<":"<<capacity<<":"<<xn<<":"<<yn<<"\n";return 1;}++bounded_cases;}}
 for(unsigned kind=0;kind<6;++kind){std::string a="boundary",b="host",c="file",d="application/octet-stream";size_t number=kind==1?65535:std::numeric_limits<size_t>::max();errno=17;auto x=native::bounded(kind,a,b,c,d,number,nullptr,0);int e=errno;errno=17;auto y=rust::bounded(kind,a,b,c,d,number,nullptr,0);if(x!=y||errno!=e)return 1;}
 char defensive[16];auto absent=swr_v1_clients_format_span{nullptr,0};auto bad=swr_v1_clients_format_span{nullptr,1};auto invalid=swr_v1_clients_http_format(2,bad,absent,absent,absent,0,reinterpret_cast<uint8_t*>(defensive),sizeof(defensive));if(invalid.error!=1||invalid.written!=0||defensive[0]!=0)return 1;invalid=swr_v1_clients_http_format(0,absent,absent,absent,absent,0,nullptr,1);if(invalid.error!=1||invalid.written!=0)return 1;
 std::cout<<"{\"actual_caller_cases\":"<<caller_cases<<",\"bounded_capacity_cases\":"<<bounded_cases<<",\"null_output_cases\":6,\"rust_only_invalid_span_cases\":2}\n";}'''
 # Each side in its own translation unit: the native one sees only pinned text.
 native,rust=out/'native_http_format.cpp',out/'actual_http_format.cpp'
 native.write_text(block('native',before));rust.write_text(block('rust',after)+entry+driver)
 exe=out/'actual_http_format';flags=['-std=c++17','-O1',*(['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if a.sanitize else [])]
 gate.run(['c++',*flags,'-c',native,'-o',out/'native_http_format.o'])
 gate.run(['c++',*flags,*hybrid_flags,rust,out/'native_http_format.o',a.archive,'-lpthread','-ldl','-lm','-o',exe]);result=json.loads(gate.run([exe]))
 report=dict(passed=True,results=result,scope=__doc__,pin=gate.PIN,hybrid_tree=str(hybrid_source),native_sanitized=a.sanitize,rust_sanitized=a.rust_sanitized);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
