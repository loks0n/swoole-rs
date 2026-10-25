<?php
// Loaded metadata only. No frontend instances, callbacks, Coroutine/Event or IO execution.
$shortnames = (int) $argv[1];
if ((int) SWOOLE_USE_SHORTNAME !== $shortnames) {
    throw new RuntimeException('Requested startup shortname configuration was not applied');
}
$names = [
    'Swoole\\Coroutine', 'Swoole\\Coroutine\\Iterator', 'Swoole\\Coroutine\\Context',
    'Swoole\\ExitException', 'Swoole\\Coroutine\\CanceledException',
    'Swoole\\Coroutine\\TimeoutException', 'Swoole\\Coroutine\\Scheduler', 'Swoole\\Coroutine\\System',
];
$aliases = ['Co' => $names[0], 'Co\\Iterator' => $names[1], 'Co\\Context' => $names[2],
    'Co\\Scheduler' => $names[6], 'Co\\System' => $names[7]];
$classes = [];
foreach ($names as $name) {
    if (!class_exists($name, false)) {
        throw new RuntimeException('Missing registered class: ' . $name);
    }
    $class = new ReflectionClass($name);
    $methods = [];
    foreach ($class->getMethods() as $method) {
        $methods[] = [$method->getName(), $method->getModifiers(), $method->getDeclaringClass()->getName()];
    }
    $parent = $class->getParentClass();
    $classes[$name] = ['name' => $class->getName(), 'parent' => $parent ? $parent->getName() : null,
        'modifiers' => $class->getModifiers(), 'default_properties' => $class->getDefaultProperties(),
        'constants' => $class->getConstants(), 'methods' => $methods];
}
foreach ($aliases as $alias => $canonical) {
    if (class_exists($alias, false) !== (bool) $shortnames) {
        throw new RuntimeException('Unexpected startup alias presence: ' . $alias);
    }
    if ($shortnames && (new ReflectionClass($alias))->getName() !== $canonical) {
        throw new RuntimeException('Alias points to another class: ' . $alias);
    }
}
$filteredNames = [];
foreach (array_merge($names, array_keys($aliases)) as $name) $filteredNames[] = strtolower($name);
$declarations = [];
foreach (get_declared_classes() as $name) {
    if (in_array(strtolower($name), $filteredNames, true)) $declarations[] = $name;
}
$constantNames = ['SWOOLE_DEFAULT_MAX_CORO_NUM', 'SWOOLE_CORO_MAX_NUM_LIMIT', 'SWOOLE_CORO_INIT',
    'SWOOLE_CORO_WAITING', 'SWOOLE_CORO_RUNNING', 'SWOOLE_CORO_END', 'SWOOLE_EXIT_IN_COROUTINE', 'SWOOLE_EXIT_IN_SERVER'];
$constants = [];
foreach (get_defined_constants() as $name => $value) {
    if (in_array($name, $constantNames, true)) {
        if (!is_int($value)) throw new RuntimeException('Expected registered integer: ' . $name);
        $constants[$name] = $value;
    }
}
if (count($constants) !== count($constantNames)) throw new RuntimeException('Missing startup constant');
echo json_encode(['shortnames' => $shortnames, 'declared_classes' => $declarations,
    'classes' => $classes, 'constants' => $constants], JSON_THROW_ON_ERROR), "\n";
