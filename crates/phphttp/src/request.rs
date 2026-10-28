//! `Swoole\Http\Request`.
use crate::{
    context::{self, Holder},
    host::{
        self, COMPLETED, Context, HTTP_CONTEXT_UNAVAILABLE, HTTP2, swr_http_host_request_body,
        swr_http_host_request_create, swr_http_host_request_data, swr_http_host_request_free,
        swr_http_host_request_method, swr_http_host_request_parse,
    },
};
use std::{ptr, slice};
use swoole_rs_zend::{
    Call, Class, declare_long, declare_null, handlers,
    sys::{IS_STRING, ZEND_ACC_PUBLIC, zend_class_entry, zend_function_entry, zend_object},
    type_of,
};

static REQUEST: Class = Class::new();

unsafe extern "C" fn create(ce: *mut zend_class_entry) -> *mut zend_object {
    // SAFETY: Zend calls `create_object` with this class or a subclass of it.
    unsafe { context::create(&REQUEST, ce) }
}

unsafe extern "C" fn free(std: *mut zend_object) {
    // SAFETY: Zend frees an object this class created.
    let ctx = unsafe { *Holder::data(std) };
    if !ctx.is_null() {
        // SAFETY: the context the object holds; C++ releases it.
        unsafe { swr_http_host_request_free(ctx) };
    }
    // SAFETY: as above.
    unsafe { Holder::dtor(std) };
}

/// MINIT: register the class as `php_swoole_http_request_minit` did.
/// # Safety
/// Called once, at MINIT, with a static `PHP_FE_END`-terminated method table.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphttp_request_minit(
    methods: *const zend_function_entry,
) -> *mut zend_class_entry {
    // SAFETY: MINIT, with the caller's table.
    unsafe {
        REQUEST.register(c"Swoole\\Http\\Request", methods, |entry, handlers| {
            context::configure(entry, handlers, create, free);
        });
    }
    let ce = REQUEST.entry();
    for name in [c"fd", c"streamId"] {
        // SAFETY: MINIT, with the class just registered.
        unsafe { declare_long(ce, name, 0, ZEND_ACC_PUBLIC) };
    }
    for name in [
        c"header",
        c"server",
        c"cookie",
        c"get",
        c"files",
        c"post",
        c"tmpfiles",
    ] {
        // SAFETY: as above.
        unsafe { declare_null(ce, name) };
    }
    ce
}

/// `http_request_get_and_check_context`.
fn checked(call: &Call) -> Option<*mut Context> {
    let ctx = context::this(call);
    if ctx.is_null() {
        host::set_last_error(HTTP_CONTEXT_UNAVAILABLE);
        call.set_bool(false);
        return None;
    }
    Some(ctx)
}

fn get_content(call: &Call) {
    let Some(ctx) = checked(call) else { return };
    let mut length = 0;
    // SAFETY: a live context and a writable length.
    let body = unsafe { swr_http_host_request_body(ctx, &raw mut length) };
    if body.is_null() {
        return call.set_empty_string();
    }
    // SAFETY: the context's body holds `length` bytes for this call.
    call.set_bytes(unsafe { slice::from_raw_parts(body.cast(), length) });
}

fn get_data(call: &Call) {
    let Some(ctx) = checked(call) else { return };
    if host::flags(ctx) & HTTP2 != 0 {
        host::fatal("unable to get data from HTTP2 request");
        return call.set_bool(false);
    }
    // SAFETY: a live context.
    let data = unsafe { swr_http_host_request_data(ctx) };
    // SAFETY: the context's request data is a live zval.
    if unsafe { type_of(data) } == IS_STRING {
        // SAFETY: as above.
        return unsafe { call.set_copy(data) };
    }
    call.set_empty_string();
}

fn create_request(call: &Call) {
    let Ok(options) = call.arity(0, 1).and_then(|()| call.array_opt(1)) else {
        return call.set_bool(false);
    };
    // SAFETY: the return slot and an optional array argument of this call.
    unsafe {
        swr_http_host_request_create(call.return_value(), options.unwrap_or(ptr::null_mut()));
    }
}

fn parse(call: &Call) {
    let ctx = context::this(call);
    if ctx.is_null() {
        host::set_last_error(HTTP_CONTEXT_UNAVAILABLE);
        return call.set_bool(false);
    }
    if host::flags(ctx) & COMPLETED != 0 {
        return call.set_bool(false);
    }
    let Ok(Some(data)) = call.arity(1, 1).and_then(|()| call.string_opt(1)) else {
        return call.set_bool(false);
    };
    // SAFETY: a live context and the argument's bytes.
    call.set_long(unsafe { swr_http_host_request_parse(ctx, data.as_ptr().cast(), data.len()) });
}

fn get_method(call: &Call) {
    let Some(ctx) = checked(call) else { return };
    // SAFETY: a live context and this call's return slot.
    unsafe { swr_http_host_request_method(ctx, call.return_value()) };
}

fn is_completed(call: &Call) {
    let Some(ctx) = checked(call) else { return };
    call.set_bool(host::flags(ctx) & COMPLETED != 0);
}

handlers! {
    zim_swoole_http_request_getContent => get_content;
    zim_swoole_http_request_getData => get_data;
    zim_swoole_http_request_create => create_request;
    zim_swoole_http_request_parse => parse;
    zim_swoole_http_request_getMethod => get_method;
    zim_swoole_http_request_isCompleted => is_completed;
}
