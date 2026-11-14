# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `3de9fdc` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,949 | 15,213 | 0.9169× | 0.92× | ✅ |
| echo-1k | 17,051 | 18,165 | 0.9387× | 0.94× | ✅ |
| json | 22,096 | 23,161 | 0.9540× | 0.95× | ✅ |
| service-health | 16,531 | 17,777 | 0.9299× | 0.93× | ✅ |
| websocket | 6,633 | 8,188 | 0.8101× | 0.8× | ✅ |
| timer | 206,044 | 313,608 | 0.6570× | 0.65× | ✅ |
| app | 125,604 | 135,967 | 0.9238× | 0.93× | ✅ |
| http2 | 18,668 | 20,467 | 0.9121× | 0.91× | ✅ |
| table | 195,545 | 201,865 | 0.9687× | 0.97× | ✅ |
| channel | 137,202 | 155,174 | 0.8842× | 0.89× | ✅ |
| task | 32,489 | 33,268 | 0.9766× | 0.96× | ✅ |
| mysql | 49,634 | 51,061 | 0.9721× | 0.97× | ✅ |
| http-client | 33,888 | 35,804 | 0.9465× | 0.94× | ✅ |
| client | 18,584 | 19,753 | 0.9408× | 0.94× | ✅ |
| socket | 19,704 | 21,072 | 0.9350× | 0.92× | ✅ |
| gzip | 194,162 | 197,079 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,090 | 181,568 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,765 | 0.9899× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,228 | 0.5094× | 0.51× | ✅ |
| udp | 7,542 | 7,987 | 0.9443× | 0.93× | ✅ |
| connect | 17,732 | 18,707 | 0.9479× | 0.94× | ✅ |
| https | 108,197 | 108,813 | 0.9943× | 1.0× | ✅ |
| wss | 103,845 | 104,801 | 0.9909× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,080 | 16,963 | 0.8890× | 0.88× | ✅ |
| http2-concurrent | 361,362 | 408,881 | 0.8838× | 0.88× | ✅ |
| websocket-64k | 89,953 | 159,691 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,871 | 16,327 | 0.7270× | 0.74× | ✅ |
| upload | 413,020 | 1,322,389 | 0.3123× | 0.32× | ✅ |
| static | 27,281 | 41,010 | 0.6652× | 0.66× | ✅ |
| pgsql | 23,375 | 24,595 | 0.9504× | 0.95× | ✅ |
| sqlite | 23,540 | 25,236 | 0.9328× | 0.93× | ✅ |
| curl | 86,124 | 90,288 | 0.9539× | 0.94× | ✅ |
| dns | 231,021 | 232,629 | 0.9931× | 0.99× | ✅ |

Geometric mean 0.8579×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
