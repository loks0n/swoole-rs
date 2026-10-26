FROM gcr.io/oss-fuzz-base/base-builder-rust:v1
COPY . $SRC/swoole-rs
WORKDIR $SRC/swoole-rs
COPY .clusterfuzzlite/build.sh $SRC/
