<?php
$classes=['Swoole\\Http\\Cookie','Swoole\\Http\\Request','Swoole\\Http\\Response','Swoole\\Http\\Server','Swoole\\Coroutine\\Http\\Server'];
function type_name($x) {return $x === null ? null : (string)$x;}
$inventory=[];
foreach($classes as $name) {
 $c=new ReflectionClass($name);$methods=[];
 foreach($c->getMethods() as $m) {
  $parameters=[];
  foreach($m->getParameters() as $p) {
   $default=['available'=>$p->isDefaultValueAvailable()];
   if($default['available']){$default['value']=$p->getDefaultValue();$default['constant']=$p->isDefaultValueConstant()?$p->getDefaultValueConstantName():null;}
   $parameters[]=['name'=>$p->getName(),'type'=>type_name($p->getType()),'optional'=>$p->isOptional(),'by_reference'=>$p->isPassedByReference(),'variadic'=>$p->isVariadic(),'default'=>$default];
  }
  $methods[$m->getName()]=['declaring_class'=>$m->getDeclaringClass()->getName(),'modifiers'=>$m->getModifiers(),'return_type'=>type_name($m->getReturnType()),'returns_reference'=>$m->returnsReference(),'parameters'=>$parameters];
 }
 ksort($methods);$props=[];foreach($c->getProperties() as $p){$props[$p->getName()]=['declaring_class'=>$p->getDeclaringClass()->getName(),'modifiers'=>$p->getModifiers(),'type'=>type_name($p->getType())];}ksort($props);
 $constants=$c->getConstants();ksort($constants);$defaults=$c->getDefaultProperties();ksort($defaults);$interfaces=$c->getInterfaceNames();sort($interfaces);
 $inventory[$name]=['parent'=>($parent=$c->getParentClass())?$parent->getName():null,'modifiers'=>$c->getModifiers(),'interfaces'=>$interfaces,'constants'=>$constants,'default_properties'=>$defaults,'properties'=>$props,'methods'=>$methods];
}
echo json_encode(['php_version'=>PHP_VERSION,'classes'=>$inventory],JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR),"\n";
