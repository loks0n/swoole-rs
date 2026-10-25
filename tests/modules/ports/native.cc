// Calls the complete pinned/generated ListenPort translation unit, not a policy model.
#include "port.inc"
#include <dlfcn.h>
#include <iostream>
#include <iomanip>
#include <poll.h>

static ssize_t sentinel_length(const swoole::Protocol *, swoole::network::Socket *, swoole::PacketLength *) { return 0; }
static uint8_t sentinel_size(swoole::network::Socket *) { return 0; }
static int sentinel_package(const swoole::Protocol *, swoole::network::Socket *, const swoole::RecvData *) { return 0; }
static int sentinel_read(swoole::Reactor *, swoole::ListenPort *, swoole::Event *) { return 0; }

template<class T> static int classify(T value, std::initializer_list<T> choices) {
    int n=0; for(auto choice:choices) { if(value==choice)return n; n++; }
    std::abort();
}

int main(int argc,char **argv) {
    std::string io_profile=argc>1?argv[1]:"probe";
    using namespace swoole;
    Dl_info core{};
    if(!dladdr(reinterpret_cast<const void *>(&swoole_init),&core)||!core.dli_fname)return 2;
    std::cerr<<"CORE "<<std::quoted(core.dli_fname)<<"\n";
    swoole_init();
    swoole_set_log_level(SW_LOG_ERROR);
    uint64_t cases=0;
    for(uint32_t flags=0;flags<512;flags++)for(int length: {0,int('N')})for(unsigned eof:{0u,1u,8u,9u,255u})for(int iteration=0;iteration<2;iteration++) {
#ifndef SW_SUPPORT_DTLS
        if(flags&2)continue;
#endif
        ListenPort p(nullptr);
        p.type=flags&1 ? SW_SOCK_UDP : SW_SOCK_TCP;
#ifdef SW_SUPPORT_DTLS
        if(flags&2) { p.ssl_context=std::make_shared<SSLContext>();p.ssl_context->protocols=SW_SSL_DTLS; }
#endif
        p.open_eof_check=flags&4;p.open_length_check=flags&8;p.open_http_protocol=flags&16;
        p.open_http2_protocol=flags&32;p.open_websocket_protocol=flags&64;
        p.open_mqtt_protocol=flags&128;p.open_redis_protocol=flags&256;
        p.protocol.package_length_type=length;p.protocol.package_length_size=37;
        p.protocol.package_length_offset=41;p.protocol.package_body_offset=43;p.protocol.package_eof_len=eof;
        p.protocol.get_package_length=sentinel_length;p.protocol.get_package_length_size=sentinel_size;
        p.protocol.onPackage=sentinel_package;p.onRead=sentinel_read;
        if(iteration) { p.init_protocol();p.open_eof_check=false;p.open_length_check=false; }
        p.init_protocol();
        std::cout<<flags<<' '<<length<<' '<<iteration<<' '<<eof<<' '<<p.get_protocols()<<' '
                 <<int(p.protocol.package_length_type)<<' '<<int(p.protocol.package_length_size)<<' '
                 <<p.protocol.package_length_offset<<' '<<p.protocol.package_body_offset<<' '<<int(p.protocol.package_eof_len)<<' '
                 <<classify<Protocol::LengthFunc>(p.protocol.get_package_length,{sentinel_length,Protocol::default_length_func,http_server::get_package_length,http2::get_frame_length,websocket::get_package_length,mqtt::get_package_length})<<' '
                 <<classify<uint8_t(*)(network::Socket*)>(p.protocol.get_package_length_size,{sentinel_size,http_server::get_package_length_size,nullptr})<<' '
                 <<classify<decltype(p.protocol.onPackage)>(p.protocol.onPackage,{sentinel_package,Server::dispatch_task,http_server::dispatch_frame,websocket::dispatch_frame})<<' '
                 <<classify<decltype(p.onRead)>(p.onRead,{sentinel_read,ListenPort::readable_callback_eof,ListenPort::readable_callback_length,ListenPort::readable_callback_http,ListenPort::readable_callback_redis,ListenPort::readable_callback_raw})<<'\n';
        cases++;
    }
    if(io_profile!="none") {
        Server server;
        ListenPort p(&server);
        p.host="127.0.0.1";p.port=0;p.backlog=17;
        if(p.create_socket()!=SW_OK||!p.socket||p.port<=0)return 10;
        int accepts=-1;
        if(io_profile=="probe") {
            int option_result=p.socket->get_option(SOL_SOCKET,SO_ACCEPTCONN,&accepts);
            std::cerr<<"BOUND accept query "<<option_result<<" value "<<accepts<<" errno "<<errno<<"\n";
            if(option_result<0||accepts!=0)return 11;
        }
        auto *same=p.socket;int same_fd=p.socket->get_fd();int assigned_port=p.port;
        if(p.create_socket()!=SW_OK||p.socket!=same||p.socket->get_fd()!=same_fd||p.port!=assigned_port)return 12;
#if defined(__linux__) && defined(HAVE_REUSEPORT)
        server.enable_reuse_port=true;
        if(p.create_socket()!=SW_OK||!p.socket||p.port!=assigned_port)return 13;
        int reused=0;
        if(p.socket->get_option(SOL_SOCKET,SO_REUSEPORT,&reused)<0||reused!=1)return 14;
#endif
        if(p.listen()!=SW_OK||!p.listening)return 15;
        if(io_profile=="probe") {
            if(p.socket->get_option(SOL_SOCKET,SO_ACCEPTCONN,&accepts)<0||accepts!=1)return 16;
        } else if(io_profile=="connect"||io_profile=="custody") {
            int client=::socket(AF_INET,SOCK_STREAM,0);if(client<0)return 19;
            sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(p.port);
#ifdef __APPLE__
            address.sin_len=sizeof(address);
#endif
            if(inet_pton(AF_INET,"127.0.0.1",&address.sin_addr)!=1||::connect(client,reinterpret_cast<sockaddr *>(&address),sizeof(address))<0)return 20;
            pollfd ready{p.socket->get_fd(),POLLIN,0};if(::poll(&ready,1,2000)!=1)return 21;
            int accepted=::accept(p.socket->get_fd(),nullptr,nullptr);if(accepted<0)return 22;
            ::close(accepted);::close(client);
        } else return 23;
        if(p.buffer_high_watermark!=uint32_t(p.socket_buffer_size*0.8))return 17;
        p.close_socket();if(p.socket)return 18;
        std::cout<<"SOCKET-IO "<<io_profile<<" bound repeat-listener-close\n";
        if(io_profile=="custody") {
            // All addresses/ports are ephemeral and native Socket remains authoritative.
            ListenPort udp(&server);udp.type=SW_SOCK_UDP;udp.host="127.0.0.1";udp.port=0;
            server.enable_reuse_port=false;
            if(udp.create_socket()!=SW_OK||!udp.socket||udp.port<=0)return 24;
            int fd=udp.socket->get_fd();
            int descriptor_flags=fcntl(fd,F_GETFD);int status_flags=fcntl(fd,F_GETFL);
            if(descriptor_flags<0||status_flags<0||!(descriptor_flags&FD_CLOEXEC)||!(status_flags&O_NONBLOCK))return 25;
            auto *existing=udp.socket;int bound=udp.port;
            if(udp.create_socket()!=SW_OK||udp.socket!=existing||udp.port!=bound)return 26;
            int sender=::socket(AF_INET,SOCK_DGRAM,0);if(sender<0)return 27;
            sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(bound);
#ifdef __APPLE__
            address.sin_len=sizeof(address);
#endif
            if(inet_pton(AF_INET,"127.0.0.1",&address.sin_addr)!=1)return 28;
            const char payload[]="ports-custody";
            if(::sendto(sender,payload,sizeof(payload),0,reinterpret_cast<sockaddr *>(&address),sizeof(address))!=sizeof(payload))return 29;
            pollfd ready{fd,POLLIN,0};if(::poll(&ready,1,2000)!=1)return 30;
            char received[sizeof(payload)]{};
            if(::recv(fd,received,sizeof(received),0)!=sizeof(payload)||memcmp(received,payload,sizeof(payload)))return 31;
            ::close(sender);udp.close_socket();if(udp.socket)return 32;
            std::cout<<"SOCKET-IO custody UDP flags repeat datagram close\n";

            int occupied=::socket(AF_INET,SOCK_STREAM,0);if(occupied<0)return 33;
            address.sin_port=0;
            if(::bind(occupied,reinterpret_cast<sockaddr *>(&address),sizeof(address))<0||::listen(occupied,1)<0)return 34;
            socklen_t length=sizeof(address);
            if(::getsockname(occupied,reinterpret_cast<sockaddr *>(&address),&length)<0)return 35;
            ListenPort conflict(&server);conflict.host="127.0.0.1";conflict.port=ntohs(address.sin_port);
            int requested=conflict.port;
            errno=0;
            int result=conflict.create_socket();int failure=errno;int last=swoole_get_last_error();
            // The original failure frees Socket without clearing the member. Do not dereference it.
            if(result!=SW_ERR||failure!=EADDRINUSE||last!=failure||conflict.port!=requested)return 36;
            ::close(occupied);
            std::cout<<"SOCKET-IO custody TCP bind conflict errno last-error retained-port\n";
        }
    }
    swoole_clean();
    std::cerr<<"CASES "<<cases<<"\n";
}
