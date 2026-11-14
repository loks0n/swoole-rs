# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `a24e444` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,953 | 15,210 | 0.9174× | 0.92× | ✅ |
| echo-1k | 17,055 | 18,165 | 0.9389× | 0.94× | ✅ |
| json | 22,099 | 23,161 | 0.9541× | 0.95× | ✅ |
| service-health | 16,535 | 17,773 | 0.9303× | 0.93× | ✅ |
| websocket | 6,632 | 8,191 | 0.8097× | 0.8× | ✅ |
| timer | 205,890 | 313,612 | 0.6565× | 0.65× | ✅ |
| app | 125,583 | 135,958 | 0.9237× | 0.93× | ✅ |
| http2 | 18,672 | 20,464 | 0.9124× | 0.91× | ✅ |
| table | 195,549 | 201,865 | 0.9687× | 0.97× | ✅ |
| channel | 137,202 | 155,171 | 0.8842× | 0.89× | ✅ |
| task | 32,492 | 33,268 | 0.9767× | 0.96× | ✅ |
| mysql | 49,675 | 51,064 | 0.9728× | 0.97× | ✅ |
| http-client | 33,893 | 35,797 | 0.9468× | 0.94× | ✅ |
| client | 18,584 | 19,757 | 0.9406× | 0.94× | ✅ |
| socket | 19,709 | 21,073 | 0.9353× | 0.92× | ✅ |
| gzip | 194,178 | 197,083 | 0.9853× | 0.99× | ✅ |
| websocket-deflate | 179,094 | 181,564 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,765 | 0.9899× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,231 | 0.5092× | 0.51× | ✅ |
| udp | 7,542 | 7,987 | 0.9443× | 0.93× | ✅ |
| connect | 17,732 | 18,703 | 0.9481× | 0.94× | ✅ |
| https | 108,200 | 108,810 | 0.9944× | 1.0× | ✅ |
| wss | 103,855 | 104,797 | 0.9910× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,076 | 16,959 | 0.8890× | 0.88× | ✅ |
| http2-concurrent | 361,109 | 409,073 | 0.8827× | 0.88× | ✅ |
| websocket-64k | 89,959 | 159,699 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,871 | 16,331 | 0.7269× | 0.74× | ✅ |
| upload | 413,437 | 1,322,387 | 0.3126× | 0.32× | ✅ |
| static | 27,269 | 40,987 | 0.6653× | 0.66× | ✅ |
| pgsql | 23,393 | 24,594 | 0.9512× | 0.95× | ✅ |
| sqlite | 23,565 | 25,236 | 0.9338× | 0.93× | ✅ |
| curl | 86,139 | 90,351 | 0.9534× | 0.94× | ✅ |
| dns | 231,491 | 232,891 | 0.9940× | 0.99× | ✅ |

Geometric mean 0.8579×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
