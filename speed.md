# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `26f889f` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,945 | 15,213 | 0.9166× | 0.92× | ✅ |
| echo-1k | 17,050 | 18,166 | 0.9386× | 0.94× | ✅ |
| json | 22,098 | 23,161 | 0.9541× | 0.95× | ✅ |
| service-health | 16,535 | 17,773 | 0.9303× | 0.93× | ✅ |
| websocket | 6,633 | 8,191 | 0.8097× | 0.8× | ✅ |
| timer | 205,980 | 313,627 | 0.6568× | 0.65× | ✅ |
| app | 125,517 | 135,862 | 0.9239× | 0.93× | ✅ |
| http2 | 18,673 | 20,464 | 0.9125× | 0.91× | ✅ |
| table | 195,997 | 201,865 | 0.9709× | 0.97× | ✅ |
| channel | 136,690 | 155,167 | 0.8809× | 0.89× | ✅ |
| task | 32,491 | 33,268 | 0.9766× | 0.96× | ✅ |
| mysql | 49,683 | 51,009 | 0.9740× | 0.97× | ✅ |
| http-client | 33,924 | 35,800 | 0.9476× | 0.94× | ✅ |
| client | 18,583 | 19,757 | 0.9406× | 0.94× | ✅ |
| socket | 19,704 | 21,073 | 0.9350× | 0.92× | ✅ |
| gzip | 194,166 | 197,083 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,100 | 181,572 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,765 | 0.9899× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,231 | 0.5092× | 0.51× | ✅ |
| udp | 7,508 | 7,987 | 0.9401× | 0.93× | ✅ |
| connect | 17,741 | 18,707 | 0.9484× | 0.94× | ✅ |
| https | 108,200 | 108,813 | 0.9944× | 1.0× | ✅ |
| wss | 103,851 | 104,797 | 0.9910× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,100 | 16,956 | 0.8905× | 0.88× | ✅ |
| http2-concurrent | 361,316 | 409,072 | 0.8833× | 0.88× | ✅ |
| websocket-64k | 89,960 | 159,700 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 12,078 | 16,327 | 0.7397× | 0.74× | ✅ |
| upload | 413,341 | 1,322,387 | 0.3126× | 0.32× | ✅ |
| static | 27,386 | 40,987 | 0.6682× | 0.66× | ✅ |
| pgsql | 23,376 | 24,594 | 0.9505× | 0.95× | ✅ |
| sqlite | 23,540 | 25,236 | 0.9328× | 0.93× | ✅ |
| curl | 85,939 | 90,479 | 0.9498× | 0.94× | ✅ |
| dns | 231,349 | 232,932 | 0.9932× | 0.99× | ✅ |

Geometric mean 0.8583×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
