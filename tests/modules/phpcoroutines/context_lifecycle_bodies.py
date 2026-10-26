"""Whole context policy, Native try/catch/storage/effects and existing queue custody."""
import textwrap
CTOR = 'PHPContext *PHPCoroutine::create_context(const Args *args) {'
MAIN = 'void PHPCoroutine::main_func(void *_args) {'
DESTROY = 'void PHPCoroutine::destroy_context(PHPContext *ctx) {'
REGISTER = 'void PHPCoroutine::defer(zend::Function *fci) {'


def block(text, indent):
    return textwrap.indent(textwrap.dedent(text).strip('\n'), indent)


def cases(entries, indent='    '):
    result = ''
    for name, effect in entries:
        result += indent + '    case SWR_CORO_LIFECYCLE_' + name + ': {\n'
        result += block(effect, indent + '        ') + '\n'
        if name not in ('DONE', 'CTOR_RETURN'):
            result += indent + '        break;\n'
        result += indent + '    }\n'
    return result


def drive(kind, entries, indent='    '):
    return indent + 'uint32_t stage = 0;\n' + indent + 'int64_t observation = 0;\n' + indent + 'for (;;) {\n' + indent + '    switch (swr_coro_lifecycle_next(&stage, SWR_CORO_LIFECYCLE_' + kind + ', observation)) {\n' + cases(entries, indent) + indent + '    }\n' + indent + '}\n'


