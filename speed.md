# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `a24e444` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,953 | 15,213 | 0.9172× | 0.92× | ✅ |
| echo-1k | 17,051 | 18,165 | 0.9387× | 0.94× | ✅ |
| json | 22,096 | 23,161 | 0.9540× | 0.95× | ✅ |
| service-health | 16,535 | 17,777 | 0.9301× | 0.93× | ✅ |
| websocket | 6,636 | 8,188 | 0.8105× | 0.8× | ✅ |
| timer | 205,979 | 313,868 | 0.6563× | 0.65× | ✅ |
| app | 125,600 | 135,939 | 0.9239× | 0.93× | ✅ |
| http2 | 18,684 | 20,468 | 0.9128× | 0.91× | ✅ |
| table | 195,997 | 201,865 | 0.9709× | 0.97× | ✅ |
| channel | 136,686 | 155,170 | 0.8809× | 0.89× | ✅ |
| task | 32,488 | 33,268 | 0.9766× | 0.96× | ✅ |
| mysql | 49,677 | 51,064 | 0.9728× | 0.97× | ✅ |
| http-client | 33,892 | 35,803 | 0.9466× | 0.94× | ✅ |
| client | 18,583 | 19,754 | 0.9407× | 0.94× | ✅ |
| socket | 19,704 | 21,068 | 0.9353× | 0.92× | ✅ |
| gzip | 194,162 | 197,079 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,094 | 181,572 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,762 | 0.9906× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,231 | 0.5092× | 0.51× | ✅ |
| udp | 7,542 | 7,987 | 0.9444× | 0.93× | ✅ |
| connect | 17,732 | 18,707 | 0.9479× | 0.94× | ✅ |
| https | 108,197 | 108,810 | 0.9944× | 1.0× | ✅ |
| wss | 103,855 | 104,797 | 0.9910× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,076 | 16,959 | 0.8889× | 0.88× | ✅ |
| http2-concurrent | 361,338 | 408,877 | 0.8837× | 0.88× | ✅ |
| websocket-64k | 89,960 | 159,694 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,871 | 16,331 | 0.7269× | 0.74× | ✅ |
| upload | 413,022 | 1,322,387 | 0.3123× | 0.32× | ✅ |
| static | 27,281 | 40,981 | 0.6657× | 0.66× | ✅ |
| pgsql | 23,395 | 24,594 | 0.9512× | 0.95× | ✅ |
| sqlite | 23,558 | 25,221 | 0.9340× | 0.93× | ✅ |
| curl | 86,140 | 90,483 | 0.9520× | 0.94× | ✅ |
| dns | 231,408 | 233,160 | 0.9925× | 0.99× | ✅ |

Geometric mean 0.8579×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
