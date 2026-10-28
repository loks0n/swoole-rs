#include "swoole_protocol.h"
#include "swoole_mime_type.h"
#include <iomanip>
#include <random>
std::string events;
bool allocation_failure;
using namespace swoole;
static int callback_mode, count, length_mode, dynamic_mode;
static Protocol *mutating_protocol;
static uint8_t dynamic(network::Socket *) {
    event("dynamic");
    if (dynamic_mode == 254) {
        mutating_protocol->package_length_offset = 5;
        mutating_protocol->package_body_offset = 3;
        return 1;
    }
    return dynamic_mode;
}
static ssize_t length_callback(const Protocol *p, network::Socket *s, PacketLength *pl) {
    message("length:%u:%u", pl->buf_size, pl->header_len);
    if (length_mode == 0) return Protocol::default_length_func(p, s, pl);
    if (length_mode == 1) return -1;
    if (length_mode == 2) return 0;
    if (length_mode == 3) return p->package_max_length + 1;
    if (length_mode == 4) return 2;
    return 8;
}
static int package(const Protocol *p, network::Socket *s, const RecvData *r) {
    message("package:%u", r->info.len);
    for (size_t i = 0; i < r->info.len; i++) message("%02x", (unsigned char) r->data[i]);
    count++;
    if (callback_mode == 1) return -1;
    if (callback_mode == 2) s->removed = true;
    if (callback_mode == 3) { s->removed = true; return -1; }
    if (callback_mode == 4) const_cast<Protocol *>(p)->package_max_length = 1;
    if (callback_mode == 5) const_cast<Protocol *>(p)->package_eof_len = 1;
    if (callback_mode == 6) {
        event("reenter"); Protocol nested = *p; network::Socket child; String bytes(16);
        child.chunks = {"nested\r\n"}; nested.split_by_eof = false; nested.package_eof_len = 2;
        callback_mode = 0; nested.recv_with_eof_protocol(&child, &bytes); callback_mode = 6;
    }
    return 0;
}
static void hex(const std::string &s) {
    for (unsigned char c: s) std::cout << std::hex << std::setw(2) << std::setfill('0') << (unsigned) c;
    std::cout << std::dec;
}
int main() {
    std::mt19937 rng(89119);
    // Real pinned definitions, all widths, native endian and unaligned buffers.
    for (int j = 0; j < 5000; j++) {
        unsigned char bytes[16]; for (auto &c: bytes) c = rng();
        for (char format: std::string("cCsSnviIlLNVqQJP?")) std::cout << "u:" << swoole_unpack(format, bytes + j % 8) << '\n';
        auto n = (uint64_t(rng()) << 32) | rng();
        std::cout << "e:" << swoole_hton64(n) << ':' << swoole_ntoh64(n) << '\n';
    }
    for (int j = 0; j < 12000; j++) {
        events.clear(); count = 0; allocation_failure = j % 17 == 0;
        int mode = rng() % 3;
        Protocol p{}; network::Socket s; String b(16 << (rng() % 3));
        p.package_length_type = "CnNsc?"[rng() % 6];
        p.package_length_size = p.package_length_type == 'n' || p.package_length_type == 's' ? 2 : p.package_length_type == 'N' ? 4 : 1;
        p.package_length_offset = rng() % 3; p.package_body_offset = 1 + rng() % 3;
        p.package_max_length = 16 << (rng() % 3);
        p.get_package_length = length_callback; p.onPackage = package;
        p.package_eof_len = 2; memcpy(p.package_eof, "\r\n", 2); p.split_by_eof = rng() % 2;
        length_mode = rng() % 6; callback_mode = rng() % 7; dynamic_mode = rng() % 5;
        // Defined-input parity: declared dynamic fields cover the actual format.
        // Short-field rejection is tested separately as a safety correction.
        if (dynamic_mode) dynamic_mode = std::max<int>(dynamic_mode, p.package_length_size);
        if (rng() % 3 == 0) p.get_package_length_size = dynamic;
        s.skip_recv = rng() % 2; s.removed = rng() % 7 == 0;
        s.caught = rng() % 5; s.error = rng() % 4 == 0 ? 0 : -1;
        int pending = rng() % 3; if (rng() % 2) s.ssl = &pending;
        b.length = rng() % 10; b.offset = b.length ? rng() % (b.length + 1) : 0;
        // recv_wait's offset is the expected complete length, never a negative extent.
        s.recv_wait = rng() % 3 == 0;
        if (s.recv_wait) b.offset = b.length + 1 + rng() % 5;
        for (size_t i = 0; i < b.length; i++) b.str[i] = "a\r\n\x02\0"[rng() % 5];
        for (int n = 0; n < 4; n++) {
            std::string chunk(1 + rng() % 9, '\0');
            for (auto &c: chunk) c = "a\r\n\x02\0"[rng() % 5];
            s.chunks.push_back(chunk);
        }
        // Keep the configured offset within the compared domain.
        if (mode == 0 && b.offset && size_t(b.offset) <= b.length) b.offset = 0;
        if (mode != 0 && b.offset > off_t(b.length)) b.offset = 0;
        int r; try { r = mode == 0 ? p.recv_with_length_protocol(&s, &b) : mode == 1 ? p.recv_with_eof_protocol(&s, &b) : p.recv_split_by_eof(&s, &b); } catch (const std::bad_alloc &) { event("bad_alloc"); r = -777; }
        std::cout << "t:" << j << ':' << r << ':' << b.length << ':' << b.size << ':' << b.offset << ':' << s.removed << s.recv_wait << s.skip_recv << ':' << count << ':';
        hex(std::string(b.str, b.length)); std::cout << ':'; hex(events); std::cout << '\n';
    }
    // Default-length captures offset before a user dynamic-size callback, then
    // observes its changed body offset. It retains the original header_len quirk.
    Protocol changing{}; network::Socket native{}; char wire[] = {4, 9, 2, 3, 4, 11};
    changing.package_length_type = 'C'; changing.package_length_size = 2;
    changing.package_length_offset = 1; changing.get_package_length_size = dynamic;
    PacketLength pl{wire, sizeof(wire), 777}; mutating_protocol = &changing;
    dynamic_mode = 254; events.clear();
    auto changed_length = Protocol::default_length_func(&changing, &native, &pl);
    assert(changed_length == 12 && pl.header_len == 2);
    std::cout << "changing:" << changed_length << ':' << pl.header_len << ':'; hex(events); std::cout << '\n';
    // Native reference storage, catalog order/buckets and identity survive rehash.
    auto &catalog = mime_type::list();
    std::cout << "catalog:" << catalog.size() << ':' << catalog.bucket_count() << '\n';
    for (auto &p: catalog) { hex(p.first); std::cout << ':'; hex(p.second); std::cout << '\n'; }
    const auto *ref = &mime_type::get("a.html");
    assert(ref == &catalog.at("html"));
    assert(&mime_type::list() == &catalog);
    for (int n = 0; n < 3000; n++) {
        std::string key = "x" + std::to_string(n);
        std::cout << "add:" << mime_type::add(key, "test") << mime_type::add(key, "duplicate") << '\n';
    }
    assert(ref == &mime_type::get("A.HTML"));
    mime_type::set("html", "new"); assert(ref == &mime_type::get("a.html") && *ref == "new");
    for (auto s: {std::string(), std::string("HTML"), std::string("a."), std::string(".HtMl"), std::string("a.html\0x", 8), std::string("A.X2")}) {
        std::cout << "lookup:" << mime_type::exists(s) << ':'; hex(mime_type::get(s)); std::cout << '\n';
    }
    mime_type::set("HTML", "uppercase"); assert(mime_type::get("HTML") == "new");
    assert(mime_type::del("HTML") && !mime_type::del("HTML"));
    assert(mime_type::del("html")); assert(mime_type::get("a.html") == "application/octet-stream");
    std::cout << "identity:pass\n";
}
