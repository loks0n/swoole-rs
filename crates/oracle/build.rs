// upstream/ holds unmodified files from Swoole v6.2.4 (c7e51450); see src/lib.rs.
use std::{env, fs, path::PathBuf};

fn out(name: &str) -> PathBuf {
    PathBuf::from(env::var("OUT_DIR").unwrap()).join(name)
}

/// An overlay patch applied to the text of its one vendored original, hunk by
/// hunk, checking every context and removed line.
fn apply(original: &str, patch: &str) -> String {
    assert_eq!(patch.matches("\n+++ ").count(), 1, "one file per patch");
    let lines: Vec<&str> = original.lines().collect();
    let (mut output, mut cursor) = (Vec::new(), 0);
    let mut hunks = patch
        .lines()
        .skip_while(|line| !line.starts_with("@@ "))
        .peekable();
    while let Some(header) = hunks.next() {
        let old = header.split(' ').nth(1).unwrap().trim_start_matches('-');
        let (start, length) = old.split_once(',').unwrap_or((old, "1"));
        let (start, length): (usize, usize) = (start.parse().unwrap(), length.parse().unwrap());
        let at = if length == 0 { start } else { start - 1 };
        let mut body = Vec::new();
        while let Some(line) = hunks.next_if(|line| !line.starts_with("@@ ")) {
            if !line.starts_with('\\') {
                body.push(if line.is_empty() { " " } else { line });
            }
        }
        let old_side: Vec<&str> = body
            .iter()
            .filter(|l| !l.starts_with('+'))
            .map(|l| &l[1..])
            .collect();
        assert_eq!(
            old_side,
            lines[at..at + length],
            "patch context matches original at {header}"
        );
        output.extend_from_slice(&lines[cursor..at]);
        output.extend(body.iter().filter(|l| !l.starts_with('-')).map(|l| &l[1..]));
        cursor = at + length;
    }
    output.extend_from_slice(&lines[cursor..]);
    output.iter().map(|line| format!("{line}\n")).collect()
}

/// Apply an overlay patch to its vendored original, so the adapter compiled here
/// is exactly the file the hybrid build compiles.
fn patched(original: &str, patch: &str, name: &str) -> PathBuf {
    println!("cargo:rerun-if-changed={patch}");
    let patch = fs::read_to_string(patch).expect("overlay patch");
    let original = fs::read_to_string(original).expect("vendored original");
    let path = out(name);
    fs::write(&path, apply(&original, &patch)).unwrap();
    path
}

/// One `TEST(suite, name) { ... }` from an upstream core-test file, plus the
/// file-scope `static const` fixtures it may use.
fn original_test(file: &str, test: &str, name: &str) -> PathBuf {
    let source = fs::read_to_string(file).expect("vendored core test");
    let fixtures = source
        .lines()
        .filter(|line| line.starts_with("static const "));
    let start = source.find(test).expect("original test");
    let end = start + source[start..].find("\n}\n").expect("test body") + 3;
    let text: String =
        fixtures.map(|line| format!("{line}\n")).collect::<String>() + &source[start..end];
    let path = out(name);
    fs::write(&path, text).unwrap();
    path
}

/// The text of `text` from `start` up to (not including) `end`, unchanged.
fn slice(text: &str, start: &str, end: &str) -> String {
    let from = text.find(start).expect(start);
    text[from..from + text[from..].find(end).expect(end)].to_string()
}

/// The pinned HTTP cookie parser and URL decode/encode, copied unchanged for
/// shim/http.cc to compile.
fn http() {
    let source = fs::read_to_string("upstream/src/protocol/http.cc").expect("vendored http.cc");
    let text = [
        slice(
            &source,
            "void parse_cookie(",
            "bool parse_multipart_boundary(",
        ),
        slice(
            &source,
            "static int url_htoi(",
            "int Request::get_protocol()",
        ),
    ]
    .concat();
    fs::write(out("http.inc"), text).unwrap();
}

/// The definition starting at `signature`, through its matching brace.
fn definition(text: &str, signature: &str) -> String {
    let start = text.find(signature).expect(signature);
    let mut depth = 0;
    for (offset, char) in text[start..].char_indices() {
        match char {
            '{' => depth += 1,
            '}' if depth == 1 => {
                let body = &text[start..start + offset + 1];
                assert!(
                    !body.contains("\n#"),
                    "no preprocessor branches in {signature}"
                );
                return body.to_string();
            }
            '}' => depth -= 1,
            _ => {}
        }
    }
    panic!("unterminated {signature}");
}

/// Request framing from the pinned http.cc (upstream) and from it with the http
/// overlay patch applied (candidate), copied unchanged for shim/http_frame.cc,
/// with the method and version enums from the pinned swoole_http.h.
fn http_frame() {
    let patch = "../../migration/patches/http/0001-http-helpers.patch";
    println!("cargo:rerun-if-changed={patch}");
    let upstream = fs::read_to_string("upstream/src/protocol/http.cc").expect("vendored http.cc");
    let candidate = apply(&upstream, &fs::read_to_string(patch).expect("http patch"));
    for (name, text) in [("upstream", &upstream), ("candidate", &candidate)] {
        let mut parts = Vec::new();
        if text.contains("static const char *method_strings[]") {
            parts.push(slice(text, "static const char *method_strings[]", "\n};") + "\n};");
        }
        if text.contains("int frame_request(") {
            parts.push(definition(text, "int frame_request("));
        }
        for signature in [
            "int Request::get_protocol(",
            "int Request::get_header_length(",
            "int Request::get_chunked_body_length(",
            "bool Request::has_expect_header(",
            "std::string Request::get_header(",
            "const char *get_method_string(",
        ] {
            parts.push(definition(text, signature));
        }
        fs::write(
            out(&format!("http_frame_{name}.inc")),
            parts.join("\n") + "\n",
        )
        .unwrap();
    }
    let header =
        fs::read_to_string("upstream/include/swoole_http.h").expect("vendored swoole_http.h");
    let enums = [
        slice(&header, "enum swHttpVersion {", "\n};") + "\n};\n",
        slice(&header, "enum swHttpMethod {", "\n};") + "\n};\n",
    ];
    fs::write(out("http_frame_enums.inc"), enums.concat()).unwrap();
}

/// The pinned packet length function and integer unpacking, copied unchanged for
/// shim/framing.cc to compile.
fn framing() {
    let source = fs::read_to_string("upstream/src/protocol/base.cc").expect("vendored base.cc");
    let from = source
        .find("int64_t swoole_unpack(")
        .expect("swoole_unpack");
    let text = [
        slice(
            &source,
            "ssize_t Protocol::default_length_func(",
            "int Protocol::recv_split_by_eof(",
        ),
        source[from..].to_string(),
    ]
    .concat();
    fs::write(out("framing.inc"), text).unwrap();
}

/// The pinned WebSocket length query, mask and decoder with the header definitions
/// they use, copied unchanged for shim/websocket.cc to compile.
fn websocket() {
    let source =
        fs::read_to_string("upstream/src/protocol/websocket.cc").expect("vendored websocket.cc");
    let header =
        fs::read_to_string("upstream/include/swoole_websocket.h").expect("vendored header");
    let constants: String = header
        .lines()
        .filter(|line| line.starts_with("#define SW_WEBSOCKET_"))
        .map(|line| format!("{line}\n"))
        .collect();
    let text = [
        constants,
        slice(&header, "enum Flag {", "#define WEBSOCKET_VERSION"),
        slice(&header, "enum Opcode {", "enum CloseReason {"),
        slice(
            &header,
            "static inline bool is_control_frame",
            "static inline uint16_t get_ext_flags",
        ),
        slice(
            &source,
            "static ssize_t get_package_length_impl",
            "bool encode(",
        ),
        slice(&source, "bool decode(", "bool pack_close_frame("),
    ]
    .concat();
    fs::write(out("websocket.inc"), text).unwrap();
}

/// A C++ build that matches the Rust side's sanitizer, so `cargo fuzz`'s ASan
/// also checks the upstream code.
fn cpp() -> cc::Build {
    let mut build = cc::Build::new();
    build.cpp(true).std("c++14");
    if env::var("CARGO_CFG_SANITIZE").is_ok_and(|s| s.split(',').any(|s| s == "address")) {
        build.flag("-fsanitize=address");
        // rustc links its own ASan runtime; Apple clang would require its own by name.
        if build.get_compiler().is_like_clang() {
            build
                .flag("-mllvm")
                .flag("-asan-guard-against-version-mismatch=0");
        }
    }
    build
}

fn main() {
    println!("cargo:rerun-if-changed=upstream");
    println!("cargo:rerun-if-changed=shim");

    // The original code: base64 under `oracle::`, crc32 renamed, so both can sit
    // beside the Rust-backed `swoole::` and `swoole_crc32`.
    websocket();
    http();
    framing();
    http_frame();
    cpp()
        .define("SWR_FRAME_ENGINE", "upstream")
        .define("SWR_FRAME_INC", "\"http_frame_upstream.inc\"")
        .include("../../native/http")
        .include(env::var("OUT_DIR").unwrap())
        .file("shim/http_frame.cc")
        .compile("swoole_oracle_http_frame");
    cpp()
        .define("swoole", "oracle")
        .define("swoole_crc32", "oracle_swoole_crc32")
        .include("shim")
        .include("upstream/include")
        .file("upstream/src/core/base64.cc")
        .file("upstream/src/core/crc32.cc")
        .file("shim/oracle.cc")
        .include(env::var("OUT_DIR").unwrap())
        .file("shim/websocket.cc")
        .file("shim/http.cc")
        .file("shim/framing.cc")
        .compile("swoole_oracle");

    // The original core-test assertions, run against the adapters that forward
    // to the Rust exports. Those symbols are resolved by the test binary.
    original_test(
        "upstream/core-tests/src/core/hash.cpp",
        "TEST(hash, crc32)",
        "crc32_test.cpp",
    );
    cpp()
        .include("shim")
        .include("upstream")
        .include("upstream/include")
        .include("../../native/include")
        .include(env::var("OUT_DIR").unwrap())
        .file(patched(
            "upstream/src/core/base64.cc",
            "../../migration/patches/base64/0001-rust-base64.patch",
            "base64_adapter.cc",
        ))
        .file(patched(
            "upstream/src/core/crc32.cc",
            "../../migration/patches/crc32/0001-rust-crc32.patch",
            "crc32_adapter.cc",
        ))
        .file("shim/original.cc")
        .file("shim/original_crc32.cc")
        .compile("swoole_original_tests");

    // The candidate framing bodies call the Rust exports, resolved by the binary.
    cpp()
        .define("SWR_FRAME_ENGINE", "candidate")
        .define("SWR_FRAME_INC", "\"http_frame_candidate.inc\"")
        .include("../../native/http")
        .include(env::var("OUT_DIR").unwrap())
        .file("shim/http_frame.cc")
        .compile("swoole_candidate_http_frame");
}
