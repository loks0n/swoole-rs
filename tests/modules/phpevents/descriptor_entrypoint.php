<?php
// Ordinary startup/descriptor consumer only. No Event operation, callback,
// reactor creation, coroutine, socket, shutdown/fault/retirement probe or IPC.
$aliases=['add','del','set','wait','isset','dispatch','defer','cycle','write','exit','rshutdown'];
$catalog=[];
foreach ($aliases as $name) {
    $method=new ReflectionMethod(Swoole\Event::class,$name);
    $function=new ReflectionFunction('swoole_event_'.$name);
    if (!$method->isStatic() || $method->getNumberOfParameters()!==$function->getNumberOfParameters()
        || $method->getNumberOfRequiredParameters()!==$function->getNumberOfRequiredParameters()) {
        throw new RuntimeException('Event catalog signature differs');
    }
    $catalog[$name]=[$method->getNumberOfParameters(),$method->getNumberOfRequiredParameters()];
}
$idle_query=Swoole\Event::isset(42);
if ($idle_query!==false) throw new RuntimeException('Unexpected idle Event registration');
$scalars=[];
foreach ([0,1,42,2147483647] as $value) {
    $converted=m28_scalar_descriptor($value);
    if ($converted!==$value) throw new RuntimeException('Scalar descriptor differs');
    $scalars[]=$converted;
}
$file=fopen($argv[1],'x+b');
if (!$file || fwrite($file,"M28 ordinary file")!==17) throw new RuntimeException('Private file setup failed');
$stream=m28_stream_descriptor($file);
if ($stream!==['nonnegative'=>true,'same_descriptor'=>true,'async'=>0]) {
    throw new RuntimeException('Plain-file descriptor conversion differs');
}
rewind($file);
if (fread($file,17)!=="M28 ordinary file") throw new RuntimeException('Private file contents differ');
fclose($file);
echo json_encode(['catalog'=>$catalog,'scalars'=>$scalars,'stream'=>$stream,'idle_query'=>$idle_query],JSON_THROW_ON_ERROR),"\n";
