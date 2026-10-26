// upstream/ holds unmodified files from Swoole v6.2.4 (c7e51450); see src/lib.rs.
use std::{env, fs, path::PathBuf};

fn out(name: &str) -> PathBuf {
    PathBuf::from(env::var("OUT_DIR").unwrap()).join(name)
}

/// Apply a single-hunk overlay patch to its vendored original, so the adapter
/// compiled here is exactly the file the hybrid build compiles.
fn patched(original: &str, patch: &str, name: &str) -> PathBuf {
    println!("cargo:rerun-if-changed={patch}");
    let patch = fs::read_to_string(patch).expect("overlay patch");
    let original = fs::read_to_string(original).expect("vendored original");
    let mut hunks = patch.lines().skip_while(|line| !line.starts_with("@@ "));
    let header = hunks.next().expect("one hunk");
    let old = header.split(' ').nth(1).unwrap().trim_start_matches('-');
    let (start, length) = old.split_once(',').unwrap_or((old, "1"));
    let (start, length): (usize, usize) = (start.parse().unwrap(), length.parse().unwrap());
    let body: Vec<&str> = hunks.collect();
    assert!(
        !body.iter().any(|line| line.starts_with("@@ ")),
        "single hunk"
    );
    let lines: Vec<&str> = original.lines().collect();
    let old_side: Vec<&str> = body
        .iter()
        .filter(|l| !l.starts_with('+'))
        .map(|l| &l[1..])
        .collect();
    assert_eq!(
        old_side,
        lines[start - 1..start - 1 + length],
        "patch context matches original"
    );
    let new_side = body.iter().filter(|l| !l.starts_with('-')).map(|l| &l[1..]);
    let source: String = lines[..start - 1]
        .iter()
        .copied()
        .chain(new_side)
        .chain(lines[start - 1 + length..].iter().copied())
        .map(|line| format!("{line}\n"))
        .collect();
    let path = out(name);
    fs::write(&path, source).unwrap();
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

/// The pinned WebSocket length query, mask and decoder with the header definitions
/// they use, copied unchanged for shim/websocket.cc to compile.
fn websocket() {
    let source =
        fs::read_to_string("upstream/src/protocol/websocket.cc").expect("vendored websocket.cc");
    let header =
        fs::read_to_string("upstream/include/swoole_websocket.h").expect("vendored header");
    let slice = |text: &str, start: &str, end: &str| {
        let from = text.find(start).expect(start);
        text[from..from + text[from..].find(end).expect(end)].to_string()
    };
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
        .compile("swoole_oracle");

    // The original core-test assertions, run against the adapters that forward
    // to the Rust exports. Those symbols are resolved by the test binary.
    original_test(
        "upstream/core-tests/src/core/hash.cpp",
        "TEST(hash, crc32)",
        "crc32_test.cpp",
    );
    cpp()
        .define("SWOOLE_RS_BASE64", "1")
        .define("SWOOLE_RS_CRC32", "1")
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
}
