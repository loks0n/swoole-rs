#!/usr/bin/env python3
"""Reconstruct owned framing/MIME callers from immutable upstream Git objects."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'target/upstream/src'
import sys
sys.path.insert(0, str(ROOT))
from tools.build_upstream import COMMIT as PIN
def original(path):return subprocess.check_output(['git','-C',str(SOURCE),'show',PIN+':'+path],text=True)

BASE=r'''#include "swoole_string.h"
#include "swoole_socket.h"
#include "swoole_protocol.h"
#include "swoole_rs_framing.h"
static_assert(sizeof(int) == 4 && sizeof(size_t) == 8 && SW_BUFFER_SIZE_STD == 8192, "framing platform ABI");
namespace swoole {
#define proto_error(_sock, _error, _fmt, ...) \
    network::Address _remote_addr; \
    if (_sock->get_peer_name(&_remote_addr) < 0) { _remote_addr = _sock->info; } \
    swoole_error_log(SW_LOG_WARNING, _error, _fmt "<%s:%d>", ##__VA_ARGS__, _remote_addr.get_addr(), _remote_addr.get_port())
ssize_t Protocol::default_length_func(const Protocol *p, network::Socket *socket, PacketLength *pl) {
    uint16_t offset = p->package_length_offset;
    uint8_t size = p->get_package_length_size ? p->get_package_length_size(socket) : p->package_length_size;
    int64_t value = 0;
    int result = swr_v1_framing_default(p->package_length_type, (const uint8_t *) pl->buf, pl->buf_size,
                                      offset, size, p->package_body_offset, &value);
    if (result == -2) {
        swoole_error_log(SW_LOG_ERROR, SW_ERROR_INVALID_PARAMS, "Invalid format specifier '%c'", p->package_length_type);
    }
    if (result < 0) { return SW_ERR; }
    if (result == 0) { pl->header_len = value; return 0; }
    swoole_debug("length=%ld", value);
    pl->header_len = p->package_length_size;
    return value;
}
static int drive(const Protocol *p, network::Socket *socket, String *buffer, uint32_t mode) {
    SwrFramingState state{}; state.mode = mode;
    if (mode == 0) { state.head = p->get_package_length_size ? p->get_package_length_size(socket) : p->package_length_size; }
    int64_t result = 0;
    while (true) {
        uint32_t flags = (socket->removed ? 1 : 0) | (socket->recv_wait ? 2 : 0) | (socket->skip_recv ? 4 : 0)
                       | (socket->ssl ? 8 : 0) | (p->split_by_eof ? 16 : 0) | (p->get_package_length_size ? 32 : 0);
        SwrFramingSnapshot input{buffer->length, buffer->size, buffer->offset, result,
            (const uint8_t *) buffer->str, (const uint8_t *) p->package_eof, p->package_eof_len,
            p->package_max_length, p->package_length_offset, (uint32_t) swoole_pagesize(), flags};
        auto action = swr_v1_framing_step(&state, &input);
        switch (action.kind) {
        case 0: return action.status;
        case 1: result = socket->recv(buffer->str + buffer->length, action.value, 0); break;
        case 2: result = socket->catch_read_error(errno); break;
        case 3:
            if (action.value > buffer->size - buffer->length) { return SW_ERR; }
            buffer->length += action.value; break;
        case 4: {
            PacketLength pl{}; pl.buf = buffer->str; pl.buf_size = buffer->length;
            result = p->get_package_length(p, socket, &pl); break;
        }
        case 5: buffer->extend(action.value); break;
        case 6: socket->recv_wait = 1; buffer->offset = action.value; break;
        case 7: {
            RecvData data{}; data.info.len = action.value; data.data = buffer->str;
            result = p->onPackage(p, socket, &data); break;
        }
        case 8: socket->recv_wait = 0; break;
        case 9: buffer->reduce(action.value); break;
        case 10: buffer->clear(); break;
        case 11:
            if (mode == 2) {
                result = buffer->split(p->package_eof, p->package_eof_len, [&](const char *data, size_t len) {
                    RecvData packet{}; packet.info.len = len; packet.data = data;
                    return p->onPackage(p, socket, &packet) >= 0 && !socket->removed;
                });
            } else { result = p->recv_split_by_eof(socket, buffer); }
            break;
        case 12: buffer->offset = action.value; break;
        case 13: result = SSL_pending(socket->ssl); break;
        case 14:
            if (mode == 0) { swoole_sys_warning("recv(%d, %d) failed", socket->fd, (uint32_t) action.value); }
            else { swoole_sys_warning("recv from socket#%d failed", socket->fd); }
            break;
        case 15: {
            proto_error(socket, SW_ERROR_PACKAGE_MALFORMED_DATA, "received %zu bytes of malformed data, remote_addr=", buffer->length);
            break;
        }
        case 16:
            swoole_error_log(SW_LOG_WARNING, SW_ERROR_PACKAGE_LENGTH_NOT_FOUND,
                            "bad request, no length found in %zu bytes, remote_addr=", buffer->length);
            break;
        case 17: {
            if (mode == 0) {
                proto_error(socket, SW_ERROR_PACKAGE_LENGTH_TOO_LARGE, "the received packet length %ld is too large, remote_addr=", (long) action.value);
            } else {
                proto_error(socket, SW_ERROR_PACKAGE_LENGTH_TOO_LARGE, "The received data packet is too large, length=%lu", (unsigned long) buffer->length);
            }
            break;
        }
        case 18: socket->skip_recv = 0; break;
        default: return SW_ERR;
        }
    }
}
int Protocol::recv_split_by_eof(network::Socket *s, String *b) const { return drive(this, s, b, 2); }
int Protocol::recv_with_length_protocol(network::Socket *s, String *b) const { return drive(this, s, b, 0); }
int Protocol::recv_with_eof_protocol(network::Socket *s, String *b) const { return drive(this, s, b, 1); }
}
int64_t swoole_unpack(char type, const void *data) {
    int64_t value = -1;
    if (swr_v1_framing_unpack(type, (const uint8_t *) data, swr_v1_framing_width(type), &value) == -1) {
        swoole_error_log(SW_LOG_ERROR, SW_ERROR_INVALID_PARAMS, "Invalid format specifier '%c'", type);
    }
    return value;
}
uint64_t swoole_hton64(uint64_t value) { return swr_v1_framing_hton64(value); }
uint64_t swoole_ntoh64(uint64_t value) { return swr_v1_framing_hton64(value); }
'''

def generated():
    mime=original('src/protocol/mime_type.cc');start=mime.index('static std::unordered_map');end=mime.index('\nconst std::unordered_map',start)
    replacement=r'''static std::string copy(SwrFramingSpan value) { return std::string((const char *) value.data, value.len); }
static std::unordered_map<std::string, std::string> make_map() {
    using Item = std::pair<const std::string, std::string>;
    std::vector<Item> entries; entries.reserve(swr_v1_framing_mime_count());
    for (size_t n = 0; n < swr_v1_framing_mime_count(); n++) {
        SwrFramingSpan key{}, value{};
        if (!swr_v1_framing_mime_entry(n, &key, &value)) { throw std::logic_error("invalid MIME catalog index"); }
        entries.emplace_back(copy(key), copy(value));
    }
    return std::unordered_map<std::string, std::string>(entries.begin(), entries.end());
}
static std::unordered_map<std::string, std::string> map_ = make_map();
static const std::string octet_stream = copy(swr_v1_framing_mime_fallback());
static std::string get_suffix(const std::string &filename) {
    size_t offset = swr_v1_framing_mime_suffix_offset((const uint8_t *) filename.data(), filename.size());
    if (offset > filename.size()) { throw std::logic_error("invalid MIME suffix offset"); }
    std::string suffix(filename.size() - offset, '\0');
    size_t size = swr_v1_framing_mime_suffix((const uint8_t *) filename.data() + offset, filename.size() - offset,
                                          suffix.empty() ? nullptr : (uint8_t *) &suffix[0], suffix.size(), std::is_signed<char>::value);
    if (size > suffix.size()) { throw std::logic_error("invalid MIME suffix extent"); }
    suffix.resize(size); return suffix;
}
'''
    mime=mime[:start]+replacement+mime[end:]
    mime=mime.replace('#include <algorithm>', '#include "swoole.h"\n#include "swoole_rs_framing.h"\n#include <vector>\n#include <type_traits>\n#include <stdexcept>')
    base=original('src/protocol/base.cc');base=base[:base.index('#include')]+BASE
    return {'src/protocol/base.cc':base,'src/protocol/mime_type.cc':mime}

def main():
    folder=ROOT/'migration/patches/framing';folder.mkdir(parents=True,exist_ok=True);patches=[]
    for n,(path,changed) in enumerate(generated().items(),1):
        name=f'{n:04}-{Path(path).stem}.patch';raw=(f'diff --git a/{path} b/{path}\n'+''.join(difflib.unified_diff(original(path).splitlines(True),changed.splitlines(True),fromfile='a/'+path,tofile='b/'+path,n=1))).replace('\n \n','\n\n').encode()
        (folder/name).write_bytes(raw);patches.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'upstream_paths':[path]})
    (folder/'manifest.json').write_text(json.dumps({'upstream_commit':PIN,'patches':patches},indent=2)+'\n')
if __name__=='__main__':main()
