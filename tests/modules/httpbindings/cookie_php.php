<?php
// Actual public API consumer: binary values, warnings, repeat/reset and reentry.
use Swoole\Http\Cookie;
date_default_timezone_set('UTC');
$results=[];$warnings=[];
set_error_handler(function($severity,$message)use(&$warnings){$warnings[]=[$severity,$message];return true;});
$methods=['withName','withValue','withPath','withDomain','withSameSite','withPriority'];
for($field=0;$field<6;$field++)for($byte=0;$byte<256;$byte++)foreach([false,true]as$encode){
 $warnings=[];
 $cookie=(new Cookie($encode))->withName('name')->withValue('a b~')->withPath('/')->withDomain('example.test')->withSameSite('Lax')->withPriority('High')->withExpires(1)->withSecure(true)->withHttpOnly(true)->withPartitioned(true);
 $cookie->{$methods[$field]}('a'.chr($byte).'z');
 $first=$cookie->toString();$second=$cookie->toString();
 $cookie->reset();$cookie->withName('reset')->withValue('a b~');$reset=$cookie->toString();
 $results[]=['id'=>"$field/$byte/".(int)$encode,'first'=>$first===false?false:bin2hex($first),'second'=>$second===false?false:bin2hex($second),'reset'=>bin2hex($reset),'warnings'=>$warnings];
 unset($cookie);
}
foreach([-1,0,1,253402300800,PHP_INT_MAX]as$expires)foreach([false,true]as$encode)foreach([null,'','value']as$value){
 $warnings=[];$cookie=(new Cookie($encode))->withName('expires')->withExpires($expires);
 if($value!==null)$cookie->withValue($value);
 $out=$cookie->toString();$results[]=['id'=>"expires/$expires/".(int)$encode.'/'.($value===null?'absent':bin2hex($value)),'output'=>$out===false?false:bin2hex($out),'warnings'=>$warnings];unset($cookie);
}
restore_error_handler();
foreach(['name','value','path','domain']as$field)foreach(['reset','nested','drop-holder']as$mode){
 $warnings=[];$nested=null;$active=false;
 $cookie=(new Cookie(false))->withName('name')->withValue('value')->withPath('/')->withDomain('example.test');
 $method='with'.ucfirst($field);$cookie->$method('bad;field');$holder=$cookie;
 set_error_handler(function($severity,$message)use(&$warnings,&$cookie,&$holder,&$active,&$nested,$mode){
  $warnings[]=[$severity,$message];if($active)return true;$active=true;
  if($mode==='drop-holder'){$holder=null;gc_collect_cycles();}
  else{$cookie->reset();$cookie->withName('inner')->withValue('a b~');if($mode==='nested')$nested=$cookie->toString();}
  return true;
 });
 $out=$cookie->toString();restore_error_handler();
 $cookie->reset();$cookie->withName('after')->withValue('ok');$after=$cookie->toString();
 $results[]=['id'=>"reentry/$field/$mode",'outer'=>$out===false?false:bin2hex($out),'nested'=>$nested===null?null:bin2hex($nested),'after'=>bin2hex($after),'warnings'=>$warnings];
 unset($holder,$cookie);
}
echo json_encode(['cases'=>count($results),'results'=>$results],JSON_THROW_ON_ERROR),"\n";
