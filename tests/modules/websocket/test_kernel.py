#!/usr/bin/env python3
"""Compile and run the native ABI checks against a feature-enabled archive."""
import argparse
import os
from pathlib import Path
import shlex
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.dev_cache import compile_cached
from tools.harness import run_isolated


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive", type=Path, default=root / "target/release/libswoole_rs_ffi.a"
    )
    parser.add_argument(
        "--sanitize", action="store_true", help="instrument the C++ caller with ASan/UBSan"
    )
    parser.add_argument('--no-cache', action='store_true')
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="swr-websocket-abi-") as directory:
        binary = Path(directory) / "kernel"
        command = shlex.split(os.environ.get("CXX", "c++")) + [
            "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", str(root / "native/include"),
            str(Path(__file__).with_name("kernel.cc")), str(archive),
        ]
        if args.sanitize:
            command.append("-fsanitize=address,undefined")
        # rustc --print native-static-libs for the supported hosts. The compiler
        # driver supplies macOS libSystem; Linux also needs libdl and pthread.
        command += ["-lc", "-lm"]
        if os.uname().sysname == "Linux":
            command += ["-ldl", "-lpthread", "-lrt", "-lutil"]
        result = compile_cached(command + ["-o", str(binary)], output=binary,
                                scratch=Path(directory), cache=not args.no_cache)
        print(f"Compile: {result['seconds']:.3f}s, cache={result['cache_hit']}: {result['cache_reason']}")
        if result['returncode']:
            raise RuntimeError(result['stderr'])
        result = run_isolated([str(binary)], timeout=15)
        print(result.stdout, end='')
        if result.returncode:
            raise RuntimeError(result.stderr)


if __name__ == "__main__":
    main()
