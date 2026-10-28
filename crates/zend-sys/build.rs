//! Generate Zend bindings from `php-config --includes` and compile the C shim.

fn main() {
    println!("cargo::rerun-if-env-changed=PHP_CONFIG");
    #[cfg(feature = "php")]
    php::bind();
}

#[cfg(feature = "php")]
#[expect(
    clippy::expect_used,
    reason = "a build script reports failure by panicking"
)]
mod php {
    use std::{env, path::PathBuf, process::Command};

    fn includes() -> Vec<PathBuf> {
        let php_config = env::var("PHP_CONFIG").unwrap_or_else(|_| "php-config".into());
        let output = Command::new(&php_config)
            .arg("--includes")
            .output()
            .expect("zend-sys: cannot run php-config ($PHP_CONFIG)");
        assert!(
            output.status.success(),
            "zend-sys: {php_config} --includes failed"
        );
        String::from_utf8_lossy(&output.stdout)
            .split_whitespace()
            .filter_map(|flag| flag.strip_prefix("-I"))
            .map(PathBuf::from)
            .collect()
    }

    pub(super) fn bind() {
        for file in ["src/shim.h", "src/shim.c"] {
            println!("cargo::rerun-if-changed={file}");
        }
        let includes = includes();
        let out = PathBuf::from(env::var("OUT_DIR").expect("zend-sys: OUT_DIR"));
        bindgen::Builder::default()
            .header("src/shim.h")
            .generate_comments(false)
            .clang_args(includes.iter().map(|dir| format!("-I{}", dir.display())))
            .allowlist_function("(_?zend_|object_properties_init|php_error_docref|php_url_encode|php_format_date|php_time|swr_zend_|swr_zval_|zval_|add_assoc_|add_next_index_|add_index_).*")
            .allowlist_type("(_?zend_|_?zval).*")
            .allowlist_var(
                "(std_object_handlers|module_registry|zend_ce_.*|ZEND_ACC_.*|IS_.*|_IS_BOOL|E_.*|ZPP_ERROR_.*|CONST_.*)",
            )
            // PHP 8.5's tail-call VM types opcode handlers preserve_none, which
            // bindgen cannot express; every VM kind but SWITCH stores a pointer,
            // and the generated layout assertions catch a SWITCH build.
            .blocklist_type("zend_vm_opcode_handler_t")
            .raw_line("pub type zend_vm_opcode_handler_t = *const ::std::ffi::c_void;")
            .generate()
            .expect("zend-sys: bindgen")
            .write_to_file(out.join("bindings.rs"))
            .expect("zend-sys: write bindings");
        cc::Build::new()
            .file("src/shim.c")
            .includes(&includes)
            .warnings(true)
            .compile("swoole_rs_zend_shim");
    }
}
