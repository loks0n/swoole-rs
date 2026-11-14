# Speed vs upstream Swoole

Callgrind instructions per request (lower is better), measured by the merge tier on `edb6fee` (`benchmarks/callgrind.py`, 1000 requests). Ratio is the Cargo build ÷ upstream: below 1.00× is faster than upstream. The limit is `benchmarks/callgrind_limits/`; ✅ beats upstream, ➖ within the limit, ❌ over it.

| workload | cargo | upstream | ratio | limit | |
| --- | ---: | ---: | ---: | ---: | --- |
| plaintext | 13,949 | 15,214 | 0.9169× | 0.92× | ✅ |
| echo-1k | 17,055 | 18,165 | 0.9389× | 0.94× | ✅ |
| json | 22,099 | 23,161 | 0.9542× | 0.95× | ✅ |
| service-health | 16,535 | 17,777 | 0.9301× | 0.93× | ✅ |
| websocket | 6,636 | 8,188 | 0.8104× | 0.8× | ✅ |
| timer | 205,909 | 313,567 | 0.6567× | 0.65× | ✅ |
| app | 125,518 | 135,951 | 0.9233× | 0.93× | ✅ |
| http2 | 18,681 | 20,467 | 0.9127× | 0.91× | ✅ |
| table | 195,997 | 201,865 | 0.9709× | 0.97× | ✅ |
| channel | 136,686 | 155,170 | 0.8809× | 0.89× | ✅ |
| task | 32,488 | 33,265 | 0.9767× | 0.96× | ✅ |
| mysql | 49,680 | 51,063 | 0.9729× | 0.97× | ✅ |
| http-client | 33,889 | 35,803 | 0.9465× | 0.94× | ✅ |
| client | 18,584 | 19,757 | 0.9406× | 0.94× | ✅ |
| socket | 19,704 | 21,072 | 0.9351× | 0.92× | ✅ |
| gzip | 194,166 | 197,079 | 0.9852× | 0.99× | ✅ |
| websocket-deflate | 179,090 | 181,568 | 0.9864× | 0.99× | ✅ |
| tcp-length | 4,717 | 4,762 | 0.9906× | 0.99× | ✅ |
| tcp-eof | 5,210 | 10,228 | 0.5094× | 0.51× | ✅ |
| udp | 7,542 | 7,986 | 0.9444× | 0.93× | ✅ |
| connect | 17,732 | 18,707 | 0.9479× | 0.94× | ✅ |
| https | 108,185 | 108,806 | 0.9943× | 1.0× | ✅ |
| wss | 103,848 | 104,800 | 0.9909× | 0.99× | ✅ |
| atomic | 49,692 | 51,316 | 0.9684× | 0.97× | ✅ |
| process-mode | 15,076 | 17,028 | 0.8854× | 0.88× | ✅ |
| http2-concurrent | 360,998 | 409,074 | 0.8825× | 0.88× | ✅ |
| websocket-64k | 89,956 | 159,692 | 0.5633× | 0.57× | ✅ |
| websocket-fragmented | 11,871 | 16,331 | 0.7269× | 0.74× | ✅ |
| upload | 413,454 | 1,322,391 | 0.3127× | 0.32× | ✅ |
| static | 27,300 | 40,987 | 0.6661× | 0.66× | ✅ |
| pgsql | 23,373 | 24,597 | 0.9502× | 0.95× | ✅ |
| sqlite | 23,540 | 25,236 | 0.9328× | 0.93× | ✅ |
| curl | 86,115 | 90,296 | 0.9537× | 0.94× | ✅ |
| dns | 231,201 | 232,946 | 0.9925× | 0.99× | ✅ |

Geometric mean 0.8578×. Goal: ≤ 1.00× on every workload ([#1894](https://github.com/appwrite-labs/swoole-rs/issues/1894)).
