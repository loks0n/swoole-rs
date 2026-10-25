<?php
// Read declarations only: no Server/Port objects, sockets or user callbacks.
$class = new ReflectionClass('Swoole\\Server\\Port');
$defaults = $class->getDefaultProperties();
$properties = [];
foreach ($class->getProperties() as $property) {
    $name = $property->getName();
    $properties[] = [
        'name' => $name,
        'private' => $property->isPrivate(),
        'public' => $property->isPublic(),
        'static' => $property->isStatic(),
        'declaring_class' => $property->getDeclaringClass()->getName(),
        'has_default' => array_key_exists($name, $defaults),
        'default' => $defaults[$name],
        'type' => gettype($defaults[$name]),
    ];
}
echo json_encode(['php' => PHP_VERSION, 'zts' => PHP_ZTS, 'swoole' => phpversion('swoole'), 'properties' => $properties], JSON_THROW_ON_ERROR), "\n";
