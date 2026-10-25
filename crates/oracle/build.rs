// upstream/ holds unmodified files from Swoole v6.2.2 (8e8c4991); see src/lib.rs.
use std::{env, fs, path::PathBuf};

const PATCH: &str = "../../migration/patches/base64/0001-rust-base64.patch";

/// The overlay replaces the whole file, so its added lines are exactly the
/// adapter the hybrid build compiles.
fn adapter_from_patch() -> PathBuf {
    let patch = fs::read_to_string(PATCH).expect("base64 overlay patch");
    assert_eq!(
        patch.matches("\n@@ ").count() + patch.starts_with("@@ ") as usize,
        1,
        "single hunk"
    );
    let source: String = patch
        .lines()
        .filter(|line| line.starts_with('+') && !line.starts_with("+++"))
        .map(|line| format!("{}\n", &line[1..]))
        .collect();
    let path = PathBuf::from(env::var("OUT_DIR").unwrap()).join("base64_adapter.cc");
    fs::write(&path, source).unwrap();
    path
}

fn main() {
    println!("cargo:rerun-if-changed=upstream");
    println!("cargo:rerun-if-changed=shim");
    println!("cargo:rerun-if-changed={PATCH}");

    // The original code under `oracle::`, so it can sit beside the Rust-backed `swoole::`.
    cc::Build::new()
        .cpp(true)
        .std("c++14")
        .define("swoole", "oracle")
        .include("upstream/include")
        .file("upstream/src/core/base64.cc")
        .file("shim/oracle.cc")
        .compile("swoole_oracle");

    // The original core-test assertions, run against the adapter that forwards
    // to the Rust exports. Those symbols are resolved by the test binary.
    cc::Build::new()
        .cpp(true)
        .std("c++14")
        .define("SWOOLE_RS_BASE64", "1")
        .include("shim")
        .include("upstream")
        .include("upstream/include")
        .include("../../native/include")
        .file(adapter_from_patch())
        .file("shim/original.cc")
        .compile("swoole_original_tests");
}
