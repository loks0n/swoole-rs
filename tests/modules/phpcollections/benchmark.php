<?php
// --check performs correctness only and never reads a clock. A measurement
// token is not authority: an operator must first obtain the actual host-wide
// acknowledged lease and verify matched optimized artifact prerequisites.
function collection_benchmark(string $name, int $iterations, bool $measure): array {
    $table = null;
    if (str_starts_with($name, 'table-')) {
        $table = new Swoole\Table(128);
        if (!$table->column('n', Swoole\Table::TYPE_INT, 8)
            || !$table->column('f', Swoole\Table::TYPE_FLOAT)
            || !$table->column('s', Swoole\Table::TYPE_STRING, 32)
            || !$table->create()) {
            throw new RuntimeException('benchmark table setup failed');
        }
        if ($name !== 'table-new-writes') {
            for ($i = 0; $i < 64; ++$i) {
                if (!$table->set((string) $i, ['n'=>$i, 'f'=>$i/4, 's'=>"v\0".$i])) {
                    throw new RuntimeException('benchmark initial row failed');
                }
            }
        }
    }
    $checksum = 0;
    $start = $measure ? hrtime(true) : null;
    if ($name === 'table-new-writes' || $name === 'table-existing-writes') {
        for ($i = 0; $i < $iterations; ++$i) {
            $key = (string) ($i % 64);
            if ($name === 'table-new-writes') { $table->del($key); }
            $checksum += (int) $table->set($key, ['n'=>$i, 'f'=>$i/4, 's'=>"v\0".$i]);
        }
        $expected = $iterations;
    } elseif ($name === 'table-full-reads' || $name === 'table-field-reads') {
        for ($i = 0; $i < $iterations; ++$i) {
            $key = (string) ($i % 64);
            if ($name === 'table-full-reads') {
                $value = $table->get($key);
                $checksum += $value['n'] + (int) ($value['f']*4) + strlen($value['s']);
            } else {
                $checksum += $table->get($key, 'n') + (int) ($table->get($key, 'f')*4)
                    + strlen($table->get($key, 's'));
            }
        }
        $cycles = intdiv($iterations, 64);
        $tail = $iterations % 64;
        $indices = $cycles*2016 + intdiv($tail*($tail-1), 2);
        $lengths = $cycles*246 + min($tail, 10)*3 + max($tail-10, 0)*4;
        $expected = 2*$indices + $lengths;
    } elseif ($name === 'table-arithmetic') {
        for ($i = 0; $i < $iterations; ++$i) {
            $checksum += $table->incr('0', 'n', 1);
            $table->incr('0', 'f', 0.25);
        }
        $expected = intdiv($iterations*($iterations+1), 2);
    } elseif ($name === 'channel-buffered') {
        Swoole\Coroutine\run(function () use ($iterations, &$checksum): void {
            $channel = new Swoole\Coroutine\Channel(16);
            for ($base = 0; $base < $iterations; $base += 16) {
                $count = min(16, $iterations-$base);
                for ($i = 0; $i < $count; ++$i) {
                    if (!$channel->push($base+$i)) { throw new RuntimeException('buffered push failed'); }
                }
                for ($i = 0; $i < $count; ++$i) { $checksum += $channel->pop(); }
            }
            if (!$channel->isEmpty() || $channel->errCode !== SWOOLE_CHANNEL_OK) {
                throw new RuntimeException('buffered channel did not drain');
            }
        });
        $expected = intdiv($iterations*($iterations-1), 2);
    } elseif ($name === 'channel-handoff') {
        Swoole\Coroutine\run(function () use ($iterations, &$checksum): void {
            $channel = new Swoole\Coroutine\Channel(1);
            $done = new Swoole\Coroutine\Channel(1);
            Swoole\Coroutine::create(function () use ($channel, $done, $iterations): void {
                $sum = 0;
                for ($i = 0; $i < $iterations; ++$i) { $sum += $channel->pop(); }
                $done->push($sum);
            });
            for ($i = 0; $i < $iterations; ++$i) {
                if (!$channel->push($i)) { throw new RuntimeException('handoff push failed'); }
            }
            $checksum = $done->pop();
            if ($done->errCode !== SWOOLE_CHANNEL_OK || !$channel->isEmpty()) {
                throw new RuntimeException('handoff channel did not drain');
            }
        });
        $expected = intdiv($iterations*($iterations-1), 2);
    } else {
        throw new InvalidArgumentException('unknown workload');
    }
    $elapsed = $measure ? hrtime(true)-$start : null;
    if ($checksum !== $expected) { throw new RuntimeException('workload checksum differs: '.$name); }
    if ($table) {
        if ($name === 'table-new-writes' || $name === 'table-existing-writes') {
            $last = $iterations-1;
            if ($table->get((string) ($last%64)) !== ['n'=>$last,'f'=>(float) ($last/4),'s'=>"v\0".$last]) {
                throw new RuntimeException('write observation differs');
            }
        }
        if ($name === 'table-arithmetic' &&
            ($table->get('0', 'n') !== $iterations || $table->get('0', 'f') !== (float) ($iterations/4))) {
            throw new RuntimeException('arithmetic observation differs');
        }
        $table->destroy();
    }
    return ['workload'=>$name, 'iterations'=>$iterations, 'checksum'=>$checksum,
        'expected'=>$expected, 'elapsed_ns'=>$elapsed, 'measurement_performed'=>$measure];
}
$workloads = ['table-new-writes', 'table-existing-writes', 'table-full-reads',
    'table-field-reads', 'table-arithmetic', 'channel-buffered', 'channel-handoff'];
$mode = $argv[1] ?? '--check';
if ($mode === '--check') {
    $results = [];
    foreach ($workloads as $name) {
        foreach ([1, 17, 64, 129] as $iterations) {
            $results[] = collection_benchmark($name, $iterations, false);
        }
    }
    echo json_encode(['passed'=>true, 'measurement_performed'=>false, 'checks'=>$results]), "\n";
} elseif ($mode === '--measure' && ($argv[4] ?? '') === 'ACKNOWLEDGED_HOST_LEASE') {
    $name = $argv[2] ?? '';
    $raw = $argv[3] ?? '';
    if (!in_array($name, $workloads, true) || !preg_match('/^[0-9]+$/D', $raw) || (int) $raw < 1 || (int) $raw > 1000000) {
        throw new InvalidArgumentException('bounded named workload/iteration count required');
    }
    echo json_encode(collection_benchmark($name, (int) $raw, true)), "\n";
} else {
    fwrite(STDERR, 'Use --check, or --measure NAME ITERATIONS ACKNOWLEDGED_HOST_LEASE only after actual exclusive acknowledgment and matched optimized prerequisites.' . "\n");
    exit(2);
}
