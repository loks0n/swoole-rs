# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `a24e444` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,953 | 15,214 | 0.9171× | 0.92× | ✅ |
| echo-1k | 17,055 | 18,165 | 0.9389× | 0.94× | ✅ |
| json | 22,096 | 23,162 | 0.9540× | 0.95× | ✅ |
| service-health | 16,531 | 17,777 | 0.9299× | 0.93× | ✅ |
| websocket | 6,632 | 8,188 | 0.8100× | 0.8× | ✅ |
| timer | 205,951 | 313,564 | 0.6568× | 0.65× | ✅ |
| app | 125,538 | 135,879 | 0.9239× | 0.93× | ✅ |
| http2 | 18,672 | 20,464 | 0.9124× | 0.91× | ✅ |
| table | 195,997 | 201,869 | 0.9709× | 0.97× | ✅ |
| channel | 136,690 | 155,170 | 0.8809× | 0.89× | ✅ |
| task | 32,489 | 33,265 | 0.9767× | 0.96× | ✅ |
| mysql | 49,677 | 51,061 | 0.9729× | 0.97× | ✅ |
| http-client | 33,895 | 35,800 | 0.9468× | 0.94× | ✅ |
| client | 18,583 | 19,757 | 0.9406× | 0.94× | ✅ |
| socket | 19,701 | 21,069 | 0.9350× | 0.92× | ✅ |
| gzip | 194,162 | 197,083 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,094 | 181,572 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,762 | 0.9906× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,231 | 0.5092× | 0.51× | ✅ |
| udp | 7,542 | 7,987 | 0.9443× | 0.93× | ✅ |
| connect | 17,733 | 18,707 | 0.9479× | 0.94× | ✅ |
| https | 108,197 | 108,803 | 0.9944× | 1.0× | ✅ |
| wss | 103,856 | 104,794 | 0.9910× | 0.99× | ✅ |
| atomic | 49,688 | 51,316 | 0.9683× | 0.97× | ✅ |
| process-mode | 15,080 | 17,025 | 0.8858× | 0.88× | ✅ |
| http2-concurrent | 360,992 | 408,877 | 0.8829× | 0.88× | ✅ |
| websocket-64k | 89,960 | 159,697 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,871 | 16,331 | 0.7269× | 0.74× | ✅ |
| upload | 413,020 | 1,322,387 | 0.3123× | 0.32× | ✅ |
| static | 27,310 | 41,010 | 0.6659× | 0.66× | ✅ |
| pgsql | 23,372 | 24,595 | 0.9503× | 0.95× | ✅ |
| sqlite | 23,540 | 25,236 | 0.9328× | 0.93× | ✅ |
| curl | 86,116 | 90,451 | 0.9521× | 0.94× | ✅ |
| dns | 231,874 | 233,415 | 0.9934× | 0.99× | ✅ |

Geometric mean 0.8577×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
