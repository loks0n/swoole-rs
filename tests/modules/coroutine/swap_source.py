"""Exact whole callback identity/dispatch closure; no Native invocation is run."""
import re
from ordered_gate import block
from make_coroutine_swap import GUARD,ALIAS_GUARD,dispatch_prefix

PATTERN=re.compile(r'#if defined\(SWOOLE_RS_COROUTINE\) && SWOOLE_RS_COROUTINE // SWR_SWAP_BEGIN\n(.*?)\n#else // SWR_SWAP_NATIVE\n(.*?)\n#endif // SWR_SWAP_END',re.S)


def restore_swap(after_source,after_header,before_source):
    source=after_source
    for name in ['yield','resume','close']:
        sig='void Coroutine::'+name+'()'
        source=source.replace(block(source,sig),block(before_source,sig),1)
    source=PATTERN.sub(lambda m:m[2],source)
    header=PATTERN.sub(lambda m:m[2],after_header).replace(GUARD,'',1).replace(ALIAS_GUARD,'',1)
    return source,header


def verify_swap(before_source,after_source,before_header,after_header):
    source,header=restore_swap(after_source,after_header,before_source)
    if source!=before_source or header!=before_header:
        raise ValueError('Unrelated source/header changed outside whole swap closure')
    if after_header.count(GUARD)!=1 or after_header.count(ALIAS_GUARD)!=1:
        raise ValueError('Function pointer size/alignment/type/linkage compiler guards missing')
    if len(list(PATTERN.finditer(after_source)))!=6 or len(list(PATTERN.finditer(after_header)))!=3:
        raise ValueError('Whole3callback constant-seed/static/setter closure missing')
    for name,op in [('yield','YIELD'),('resume','RESUME'),('close','CLOSE')]:
        signature='void Coroutine::'+name+'()';before=block(before_source,signature);after=block(after_source,signature)
        start=before.index('    const auto plan = ');end=before.index('SWR_CO_STATUS_PUBLISH);',start)+len('SWR_CO_STATUS_PUBLISH);')
        inverse=after.replace(dispatch_prefix(name,op),before[start:end],1)
        inverse=inverse.replace('dispatch.function(dispatch.task)','on_'+name+'(get_task())',1)
        if inverse!=before:raise ValueError('Native effect or fresh observation order changed')
        old='SW_THREAD_LOCAL Coroutine::SwapCallback Coroutine::on_'+name+' = nullptr;'
        new='SW_THREAD_LOCAL swr_v1_coroutine_swap_callback Coroutine::on_'+name+' = {nullptr};'
        if not any(m[1]==new and m[2]==old for m in PATTERN.finditer(after_source)):
            raise ValueError('Native TLS/constantnull typed function seed changed')
    return dict(source_closure=True,header_closure=True,native_effect_bodies_byte_equal_after_descriptor_inverse=True,
                function_pointer_laundering=False,callback_invocations_executed=False,runtime_executed=False)
