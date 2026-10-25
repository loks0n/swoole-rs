# String native performance

macOS ARM64 native consumers (`gate.py --prepare-benchmark` then `benchmark.py`),
C++ `-O3` without sanitizers, nine rotated/reversed trials per workload, latest sample per workload. These are
not PHP throughput. Ratio is upstream time / Rust time; higher is better.

| Workload | Upstream/Rust |
| --- | ---: |
| Warm append 4 KiB | 1.04 |
| Cold append/growth | 0.74 |
| Repeat 4 KiB | 1.16 |
| Write/reduce | 0.89 |
| Binary queries 4 KiB | 4.97 |
| Sixteen split frames | 5.51 |
| Missing delimiter | 11.34 |
| Dense repeated prefix, short needle | 14.32 |
| Dense repeated prefix, long needle | 18.84 |

Search uses `memchr::memmem`; a hand-written `memchr` scanner was rejected after
it measured 25 microseconds per dense-needle cycle versus 0.1 for memmem.

Integer append via `itoa` with a separate copy measured 0.55x upstream; the
current fused in-place append has not been timed.

Cold growth and write/reduce block default activation.

For the queue, `Buffer::appendv` keeps an `inline(always)` hint (about +8% on
contiguous 4 KiB pop, other workloads within 0.5%). A const-generic contiguous
specialization showed no consistent gain and was dropped.
