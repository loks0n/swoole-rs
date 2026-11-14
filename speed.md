# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `a24e444` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,953 | 15,210 | 0.9174× | 0.92× | ✅ |
| echo-1k | 17,055 | 18,162 | 0.9390× | 0.94× | ✅ |
| json | 22,099 | 23,158 | 0.9543× | 0.95× | ✅ |
| service-health | 16,535 | 17,773 | 0.9303× | 0.93× | ✅ |
| websocket | 6,632 | 8,191 | 0.8097× | 0.8× | ✅ |
| timer | 205,946 | 313,492 | 0.6569× | 0.65× | ✅ |
| app | 125,536 | 135,912 | 0.9237× | 0.93× | ✅ |
| http2 | 18,673 | 20,463 | 0.9125× | 0.91× | ✅ |
| table | 195,997 | 201,869 | 0.9709× | 0.97× | ✅ |
| channel | 136,690 | 155,170 | 0.8809× | 0.89× | ✅ |
| task | 32,489 | 33,265 | 0.9767× | 0.96× | ✅ |
| mysql | 49,681 | 51,058 | 0.9730× | 0.97× | ✅ |
| http-client | 33,891 | 35,803 | 0.9466× | 0.94× | ✅ |
| client | 18,583 | 19,757 | 0.9406× | 0.94× | ✅ |
| socket | 19,700 | 21,072 | 0.9349× | 0.92× | ✅ |
| gzip | 194,162 | 197,083 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,094 | 181,572 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,762 | 0.9905× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,231 | 0.5092× | 0.51× | ✅ |
| udp | 7,542 | 7,987 | 0.9443× | 0.93× | ✅ |
| connect | 17,729 | 18,707 | 0.9477× | 0.94× | ✅ |
| https | 108,183 | 108,810 | 0.9942× | 1.0× | ✅ |
| wss | 103,849 | 104,794 | 0.9910× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,080 | 16,959 | 0.8892× | 0.88× | ✅ |
| http2-concurrent | 361,179 | 409,074 | 0.8829× | 0.88× | ✅ |
| websocket-64k | 89,960 | 159,696 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,871 | 16,331 | 0.7269× | 0.74× | ✅ |
| upload | 413,010 | 1,322,387 | 0.3123× | 0.32× | ✅ |
| static | 27,269 | 40,987 | 0.6653× | 0.66× | ✅ |
| pgsql | 23,395 | 24,594 | 0.9512× | 0.95× | ✅ |
| sqlite | 23,558 | 25,236 | 0.9335× | 0.93× | ✅ |
| curl | 86,132 | 90,462 | 0.9521× | 0.94× | ✅ |
| dns | 231,119 | 233,076 | 0.9916× | 0.99× | ✅ |

Geometric mean 0.8578×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
