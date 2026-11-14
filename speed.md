# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `910d3c7` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,949 | 15,210 | 0.9171× | 0.92× | ✅ |
| echo-1k | 17,055 | 18,162 | 0.9390× | 0.94× | ✅ |
| json | 22,099 | 23,158 | 0.9543× | 0.95× | ✅ |
| service-health | 16,535 | 17,777 | 0.9301× | 0.93× | ✅ |
| websocket | 6,636 | 8,188 | 0.8105× | 0.8× | ✅ |
| timer | 205,906 | 313,571 | 0.6566× | 0.65× | ✅ |
| app | 125,520 | 135,889 | 0.9237× | 0.93× | ✅ |
| http2 | 18,678 | 20,464 | 0.9127× | 0.91× | ✅ |
| table | 195,997 | 201,865 | 0.9709× | 0.97× | ✅ |
| channel | 136,686 | 155,170 | 0.8809× | 0.89× | ✅ |
| task | 32,493 | 33,264 | 0.9768× | 0.96× | ✅ |
| mysql | 49,676 | 51,035 | 0.9734× | 0.97× | ✅ |
| http-client | 33,890 | 35,800 | 0.9467× | 0.94× | ✅ |
| client | 18,580 | 19,757 | 0.9404× | 0.94× | ✅ |
| socket | 19,709 | 21,073 | 0.9353× | 0.92× | ✅ |
| gzip | 194,162 | 197,079 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,085 | 181,560 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,762 | 0.9906× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,231 | 0.5092× | 0.51× | ✅ |
| udp | 7,542 | 7,987 | 0.9443× | 0.93× | ✅ |
| connect | 17,732 | 18,707 | 0.9479× | 0.94× | ✅ |
| https | 108,197 | 108,803 | 0.9944× | 1.0× | ✅ |
| wss | 103,855 | 104,797 | 0.9910× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,076 | 16,959 | 0.8890× | 0.88× | ✅ |
| http2-concurrent | 361,208 | 409,069 | 0.8830× | 0.88× | ✅ |
| websocket-64k | 89,955 | 159,692 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,871 | 16,331 | 0.7269× | 0.74× | ✅ |
| upload | 413,437 | 1,322,387 | 0.3126× | 0.32× | ✅ |
| static | 27,298 | 41,016 | 0.6655× | 0.66× | ✅ |
| pgsql | 23,376 | 24,596 | 0.9504× | 0.95× | ✅ |
| sqlite | 23,540 | 25,236 | 0.9328× | 0.93× | ✅ |
| curl | 86,125 | 90,350 | 0.9532× | 0.94× | ✅ |
| dns | 231,283 | 233,128 | 0.9921× | 0.99× | ✅ |

Geometric mean 0.8579×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
