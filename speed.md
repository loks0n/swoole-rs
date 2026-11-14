# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `9741d69` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,945 | 15,214 | 0.9166× | 0.92× | ✅ |
| echo-1k | 17,050 | 18,165 | 0.9386× | 0.94× | ✅ |
| json | 22,116 | 23,161 | 0.9549× | 0.95× | ✅ |
| service-health | 16,549 | 17,777 | 0.9310× | 0.93× | ✅ |
| websocket | 6,633 | 8,188 | 0.8101× | 0.8× | ✅ |
| timer | 205,893 | 313,572 | 0.6566× | 0.65× | ✅ |
| app | 125,574 | 135,872 | 0.9242× | 0.93× | ✅ |
| http2 | 18,712 | 20,467 | 0.9142× | 0.91× | ✅ |
| table | 195,563 | 201,865 | 0.9688× | 0.97× | ✅ |
| channel | 137,224 | 155,174 | 0.8843× | 0.89× | ✅ |
| task | 32,492 | 33,268 | 0.9767× | 0.96× | ✅ |
| mysql | 49,678 | 51,064 | 0.9728× | 0.97× | ✅ |
| http-client | 33,921 | 35,803 | 0.9474× | 0.94× | ✅ |
| client | 18,583 | 19,757 | 0.9406× | 0.94× | ✅ |
| socket | 19,704 | 21,073 | 0.9350× | 0.92× | ✅ |
| gzip | 194,162 | 197,083 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,104 | 181,572 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,765 | 0.9899× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,231 | 0.5092× | 0.51× | ✅ |
| udp | 7,508 | 7,987 | 0.9401× | 0.93× | ✅ |
| connect | 17,741 | 18,703 | 0.9486× | 0.94× | ✅ |
| https | 108,186 | 108,810 | 0.9943× | 1.0× | ✅ |
| wss | 103,854 | 104,797 | 0.9910× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,100 | 16,959 | 0.8904× | 0.88× | ✅ |
| http2-concurrent | 361,706 | 409,069 | 0.8842× | 0.88× | ✅ |
| websocket-64k | 89,959 | 159,692 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,872 | 16,327 | 0.7271× | 0.74× | ✅ |
| upload | 413,523 | 1,322,388 | 0.3127× | 0.32× | ✅ |
| static | 27,349 | 40,993 | 0.6672× | 0.66× | ✅ |
| pgsql | 23,379 | 24,595 | 0.9505× | 0.95× | ✅ |
| sqlite | 23,536 | 25,236 | 0.9326× | 0.93× | ✅ |
| curl | 85,942 | 90,350 | 0.9512× | 0.94× | ✅ |
| dns | 231,793 | 233,007 | 0.9948× | 0.99× | ✅ |

Geometric mean 0.8580×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
