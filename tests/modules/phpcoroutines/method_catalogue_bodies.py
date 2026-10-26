"""Whole Rust method metadata with mandatory stable Native Zend ABI storage."""
import re
BRIDGE = '''
#ifdef SWOOLE_RS_PHPCOROUTINES
struct PHPCoroutineMethodBinding {
    zif_handler handler;
    const zend_internal_arg_info *arginfo;
    uint32_t arguments;
};
static void php_coroutine_project_methods(uint32_t kind, const PHPCoroutineMethodBinding *bindings,
                                          zend_function_entry *projection) {
    swr_phpcoroutines_method_cursor cursor{};
#ifdef SW_CORO_TIME
    const uint8_t capabilities = 1;
#else
    const uint8_t capabilities = 0;
#endif
    for (;;) {
        const auto method = swr_v1_phpcoroutines_method(&cursor, kind, capabilities,
                                                       ZEND_ACC_PUBLIC, ZEND_ACC_STATIC);
        if (method.done) {
            projection[method.slot] = {};
            return;
        }
        const auto &binding = bindings[method.handler];
        auto &entry = projection[method.slot];
        entry.fname = method.name;
        entry.handler = binding.handler;
        entry.arg_info = binding.arginfo;
        entry.num_args = binding.arguments;
        entry.flags = method.flags;
    }
}
#endif
'''


def declarations(source):
    return list(re.finditer(r'static (?:const|constexpr) zend_function_entry (\w+)\[\]\s*=\s*\{(.*?)\n\};', source, re.S))


def bindings(table):
    rows = []
    condition = None
    for line in table.splitlines():
        line = line.strip()
        if line.startswith('#ifdef '):
            condition = line[7:]
            if condition != 'SW_CORO_TIME': raise ValueError('New method capability requires source audit')
            continue
        if line == '#endif': condition = None; continue
        match = re.match(r'(PHP_ME|PHP_MALIAS|ZEND_FENTRY)\((.*)\)', line)
        if not match: continue
        parts = []; start = depth = 0
        for i, char in enumerate(match[2]):
            depth += (char == '(') - (char == ')')
            if char == ',' and depth == 0: parts.append(match[2][start:i].strip()); start = i + 1
        parts.append(match[2][start:].strip())
        if match[1] == 'PHP_ME': handler = 'ZEND_MN(' + parts[0] + '_' + parts[1] + ')'; info = parts[2]
        elif match[1] == 'PHP_MALIAS': handler = 'ZEND_MN(' + parts[0] + '_' + parts[2] + ')'; info = parts[3]
        else: handler, info = parts[1:3]
        if parts[-1] not in ('ZEND_ACC_PUBLIC', 'ZEND_ACC_PUBLIC | ZEND_ACC_STATIC'):
            raise ValueError('New method visibility requires source audit')
        value = f'    {{{handler}, {info}, static_cast<uint32_t>(sizeof({info}) / sizeof(zend_internal_arg_info) - 1)}},\n'
        rows.append((condition, value))
    return rows


def selected_table(table):
    name = table[1]
    rows = bindings(table[2])
    selected = '#ifdef SWOOLE_RS_PHPCOROUTINES\nstatic constexpr PHPCoroutineMethodBinding ' + name + '_bindings[] = {\n'
    for condition, value in rows:
        selected += ('#ifdef ' + condition + '\n' + value + '#else\n    {},\n#endif\n') if condition else value
    selected += '};\nstatic zend_function_entry ' + name + '[' + str(len(rows) + 1) + ']{};\n#else\n' + table[0] + '\n#endif'
    return selected


