#!/usr/bin/env python3
"""Generate real wrapper callers from immutable reference objects."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'target/upstream/src'
PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'


def original(path):
    return subprocess.check_output(['git', '-C', str(SOURCE), 'show', f'{PIN}:{path}'], text=True)


def body(text, signature, replacement):
    start = text.index(signature)
    brace = text.index('{', start)
    level = 1
    end = brace + 1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[:brace + 1] + '\n' + replacement.strip('\n') + '\n}' + text[end:]


def generated():
    event = original('src/wrapper/event.cc').replace('#include "swoole_reactor.h"', '#include "swoole_reactor.h"\n#include "swoole_rs_wrappers.h"\nstatic_assert(SW_EVENT_READ == 512 && SW_EVENT_WRITE == 1024, "wrapper event ABI");')
    event = body(event, 'int swoole_event_init(', '''    auto *reactor = new Reactor(SW_REACTOR_MAXEVENTS);
    auto plan = swr_v1_wrappers_event_init(flags, SW_EVENTLOOP_WAIT_EXIT, reactor->ready());
    if (!plan.accepted) { return SW_ERR; }
    if (plan.wait_exit) { reactor->wait_exit = true; }
    for (uint32_t initializer : plan.initializers) {
        switch (initializer) {
        case SWR_WRAPPER_INIT_SOCKET: swoole::coroutine::Socket::init_reactor(reactor); break;
        case SWR_WRAPPER_INIT_SYSTEM: swoole::coroutine::System::init_reactor(reactor); break;
        case SWR_WRAPPER_INIT_CLIENT: swoole::network::Client::init_reactor(reactor); break;
        default: assert(false); return SW_ERR;
        }
    }
    SwooleTG.reactor = reactor;
    return SW_OK;''')
    event = body(event, 'int swoole_event_add_or_update(', '''    switch (swr_v1_wrappers_event_direction(event)) {
    case 1: return SwooleTG.reactor->add_read_event(_socket);
    case 2: return SwooleTG.reactor->add_write_event(_socket);
    default: assert(0); return SW_ERR;
    }''')
    event = event.replace('if (!reactor->wait_exit or !reactor->if_exit()) {', 'if (swr_v1_wrappers_event_wait(reactor->wait_exit, reactor->wait_exit ? reactor->if_exit() : false)) {')
    http = original('src/wrapper/http.cc').replace('#include "swoole_http.h"', '#include "swoole_http.h"\n#include "swoole_rs_wrappers.h"')
    start = http.index('struct ContextImpl {')
    end = http.index('\n};', start) + 3
    http = http[:start] + '''static_assert(HTTP_DELETE == 0 && HTTP_POST == 3 && HTTP_PUT == 4 && HTTP_PATCH == 28, "wrapper method ABI");
static std::string owned(SwrWrapperSpan s) { return std::string((const char *) s.data, s.len); }
struct ContextImpl {
    llhttp_t parser{};
    multipart_parser *mt_parser = nullptr;
    SwrWrapperRequest *state = swr_v1_wrappers_request_new();
    ContextImpl() = default;
    ContextImpl(const ContextImpl &) = delete;
    ContextImpl &operator=(const ContextImpl &) = delete;
    void clear_multipart() {
        if (mt_parser) {
            if (mt_parser->fp) { fclose(mt_parser->fp); }
            multipart_parser_free(mt_parser);
            mt_parser = nullptr;
        }
    }
    ~ContextImpl() { clear_multipart(); swr_v1_wrappers_request_free(state); }
    SwrWrapperView view() const {
        SwrWrapperView v{};
        swr_v1_wrappers_request_view(state, &v);
        return v;
    }
    bool parse(Context &ctx, const char *at, size_t length) {
        if (!state) { return false; }
        swoole_llhttp_parser_init(&parser, HTTP_REQUEST, static_cast<void *>(&ctx));
        swoole_llhttp_parser_execute(&parser, &http_parser_settings, at, length);
        return parser.error == HPE_OK && (view().flags & 1);
    }
};''' + http[end:]
    http = body(http, 'static int http_request_on_url(llhttp_t *parser, const char *at, size_t length) {', '''    size_t path_len = swr_v1_wrappers_split((const uint8_t *) at, length, '?');
    auto *ctx = static_cast<Context *>(parser->data);
    ctx->request_path.assign(at, path_len);
    if (path_len < length && length - path_len > 1) {
        ctx->query_string.assign(at + path_len + 1, length - path_len - 1);
    }
    return 0;''')
    http = body(http, 'static int http_request_on_header_field(llhttp_t *parser, const char *at, size_t length) {', '''    auto *ctx = static_cast<Context *>(parser->data);
    return swr_v1_wrappers_header(ctx->impl->state, (const uint8_t *) at, length);''')
    http = body(http, 'static int http_request_on_header_value(llhttp_t *parser, const char *at, size_t length) {', '''    auto *ctx = static_cast<Context *>(parser->data);
    auto *impl = ctx->impl;
    ctx->headers[owned(impl->view().header)] = std::string(at, length);
    int kind = swr_v1_wrappers_header_kind(impl->state, parser->method, (const uint8_t *) at, length, 0);
    if (kind == 1) { ctx->post_form_urlencoded = true; }
    else if (kind == 2) {
        char *boundary_str;
        int boundary_len;
        if (!parse_multipart_boundary(at, length, sizeof("multipart/form-data") - 1, &boundary_str, &boundary_len)) { return -1; }
        impl->clear_multipart();
        impl->mt_parser = multipart_parser_init(boundary_str, boundary_len, &mt_parser_settings);
        if (!impl->mt_parser) { return -1; }
        impl->mt_parser->data = ctx;
        swoole_trace_log(SW_TRACE_HTTP, "form_data, boundary_str=%s", boundary_str);
    }
    return kind < 0 ? -1 : 0;''')
    http = body(http, 'static int http_request_on_body(llhttp_t *parser, const char *at, size_t length) {', '''    if (!length) { return 0; }
    auto *ctx = static_cast<Context *>(parser->data);
    auto *impl = ctx->impl;
    if (impl->mt_parser) {
        size_t skip = swr_v1_wrappers_body_skip(impl->state, (const uint8_t *) at, length);
        at += skip; length -= skip;
        size_t n = multipart_parser_execute(impl->mt_parser, at, length);
        if (n != length) { swoole_error_log(SW_LOG_WARNING, SW_ERROR_SERVER_INVALID_REQUEST, "parse multipart body failed, %zu/%zu bytes processed", n, length); }
    } else { ctx->body.append(at, length); }
    return (impl->view().flags & 1) ? HPE_PAUSED : 0;''')
    http = body(http, 'static int multipart_body_on_header_value(multipart_parser *p, const char *at, size_t length) {', '''    auto *ctx = static_cast<Context *>(p->data);
    auto *impl = ctx->impl;
    int kind = swr_v1_wrappers_header_kind(impl->state, 0, (const uint8_t *) at, length, 1);
    if (kind == 3) {
        return swr_v1_wrappers_disposition(impl->state, (const uint8_t *) at, length);
    }
    if (kind == 4) {
        swr_v1_wrappers_complete(impl->state);
        ctx->files[owned(impl->view().form)] = std::string(at, length);
    }
    return kind < 0 ? -1 : 0;''')
    http = body(http, 'static int multipart_body_on_data(multipart_parser *p, const char *at, size_t length) {', '''    auto *ctx = static_cast<Context *>(p->data);
    auto *impl = ctx->impl;
    if (impl->view().form.len) { return swr_v1_wrappers_body_append(impl->state, (const uint8_t *) at, length); }
    if (p->fp) {
        ssize_t n = fwrite(at, sizeof(char), length, p->fp);
        if (n != (off_t) length) {
            int error = errno;
            fclose(p->fp); p->fp = nullptr;
            auto file = ctx->files.find(owned(impl->view().form));
            if (file != ctx->files.end()) { unlink(file->second.c_str()); }
            ctx->files[owned(impl->view().form)] = "ERROR(1)";
            errno = error;
            swoole_sys_warning("write upload file failed");
        }
    }
    return 0;''')
    http = body(http, 'static int multipart_body_on_header_complete(multipart_parser *p) {', '''    auto *ctx = static_cast<Context *>(p->data);
    auto view = ctx->impl->view();
    if (!view.input.len || ctx->files.find(owned(view.form)) != ctx->files.end()) { return 0; }
    char file_path[SW_HTTP_UPLOAD_TMPDIR_SIZE] = "/tmp/swoole.upfile.XXXXXX";
    int tmpfile = swoole_tmpfile(file_path);
    if (tmpfile < 0) { return 0; }
    FILE *fp = fdopen(tmpfile, "wb+");
    if (!fp) { int error = errno; close(tmpfile); unlink(file_path); errno = error; swoole_sys_warning("fopen(%s) failed", file_path); return 0; }
    try { ctx->files.emplace(owned(view.form), file_path); }
    catch (...) { int error = errno; fclose(fp); unlink(file_path); errno = error; throw; }
    p->fp = fp;
    return 0;''')
    http = body(http, 'static int multipart_body_on_data_end(multipart_parser *p) {', '''    auto *ctx = static_cast<Context *>(p->data);
    auto view = ctx->impl->view();
    if (view.form.len) { ctx->form_data[owned(view.form)] = owned(view.body); }
    if (p->fp) { fclose(p->fp); p->fp = nullptr; }
    swr_v1_wrappers_part_end(ctx->impl->state);
    return 0;''')
    http = body(http, 'static int http_request_message_complete(llhttp_t *p) {', '''    auto *ctx = static_cast<Context *>(p->data);
    swr_v1_wrappers_complete(ctx->impl->state);
    return HPE_PAUSED;''')
    http = http.replace('size_t n = sw_snprintf(buf, sizeof(buf), "%s: %s\\r\\n", iter.first.c_str(), iter.second.c_str());', 'size_t n = swr_v1_wrappers_header_wire((const uint8_t *) iter.first.data(), iter.first.size(), (const uint8_t *) iter.second.data(), iter.second.size(), (uint8_t *) buf, sizeof(buf));')
    old_length = 'response.headers["Content-Length"] = std::to_string(length);'
    assert http.count(old_length) == 1
    http = http.replace(old_length, 'static_assert(sizeof(buf) >= sizeof(size_t) * 8, "decimal length capacity");\n        size_t digits = swr_v1_wrappers_content_length(length, (uint8_t *) buf, sizeof(buf));\n        response.headers["Content-Length"] = std::string(buf, digits);')
    start = http.index('    if (!server_->send(session_id_, sw_tg_buffer()->str', http.index('bool Context::end('))
    end = http.index('\n}\n', start)
    http = http[:start] + '''    uint32_t action = SWR_WRAPPER_RESPONSE_START;
    bool succeeded = true, keepalive_snapshot = false;
    for (;;) {
        action = swr_v1_wrappers_response_next(action, length, succeeded, keepalive_snapshot);
        switch (action) {
        case SWR_WRAPPER_RESPONSE_HEADER:
            succeeded = server_->send(session_id_, sw_tg_buffer()->str, sw_tg_buffer()->length);
            if (!succeeded) swoole_warning("failed to send HTTP header");
            break;
        case SWR_WRAPPER_RESPONSE_BODY:
            succeeded = server_->send(session_id_, data, length);
            if (!succeeded) swoole_warning("failed to send HTTP body");
            break;
        case SWR_WRAPPER_RESPONSE_OBSERVE:
            keepalive_snapshot = keepalive;
            break;
        case SWR_WRAPPER_RESPONSE_CLOSE:
            server_->close(session_id_, false);
            break;
        case SWR_WRAPPER_RESPONSE_DONE:
            return true;
        default:
            return false;
        }
    }''' + http[end:]
    http = http.replace("auto index = addr.find(':');", "auto address = swr_v1_wrappers_listener_plan((const uint8_t *) addr.data(), addr.size());\n    auto index = address.separator;").replace('if (index == std::string::npos) {', 'if (!address.valid) {').replace('if (host.empty()) {','if (address.default_host) {')
    return {'src/wrapper/event.cc': event, 'src/wrapper/http.cc': http}


def main():
    directory = ROOT / 'migration/patches/wrappers'
    directory.mkdir(parents=True, exist_ok=True)
    patches = []
    for index, (path, text) in enumerate(generated().items(), 1):
        name = f'{index:04}-{Path(path).stem}.patch'
        diff = f'diff --git a/{path} b/{path}\n' + ''.join(difflib.unified_diff(original(path).splitlines(True), text.splitlines(True), fromfile='a/' + path, tofile='b/' + path, n=1))
        diff = diff.replace('\n \n', '\n\n')
        raw = diff.encode(); (directory / name).write_bytes(raw)
        patches.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'upstream_paths': [path]})
    (directory / 'manifest.json').write_text(json.dumps({'upstream_commit': PIN, 'patches': patches}, indent=2) + '\n')


if __name__ == '__main__': main()
