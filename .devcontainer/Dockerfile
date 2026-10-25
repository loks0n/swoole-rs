# The same OS and packages as the CI runners (ubuntu-24.04, PHP 8.3).
FROM ubuntu:24.04
COPY install.sh /tmp/install.sh
RUN /tmp/install.sh && rm -rf /var/lib/apt/lists/* /tmp/install.sh
# rustup installs the toolchain pinned in rust-toolchain.toml on first use.
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none \
    && chmod -R a+w /usr/local/rustup /usr/local/cargo
