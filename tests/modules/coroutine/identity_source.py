"""Whole identity closure/effect order proof; never executes Native lifecycles."""
import re
from ordered_gate import block
from make_coroutine_identity import selected

GUARD='''#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE
static_assert(sizeof(swr_v1_coroutine_identity) == sizeof(void *) && alignof(swr_v1_coroutine_identity) == alignof(void *), "Coroutine identity requires exact Native pointer ABI");
#endif
'''
PATTERN=re.compile(r'#if defined\(SWOOLE_RS_COROUTINE\) && SWOOLE_RS_COROUTINE // SWR_IDENTITY_BEGIN\n(.*?)\n#else // SWR_IDENTITY_NATIVE\n(.*?)\n#endif // SWR_IDENTITY_END',re.S)


def restore_identity(text):
    return PATTERN.sub(lambda match:match[2],text)


def verify_identity(before_source,after_source,before_header,after_header):
    if restore_identity(after_source)!=before_source:
        raise ValueError('Unrelated source bytes changed outside identity closure')
    restored=restore_identity(after_header)
    if restored.count(GUARD)!=1:raise ValueError('Pointer ABI guard missing')
    restored=restored.replace(GUARD,'',1)
    if restored!=before_header:raise ValueError('Unrelated header bytes changed outside identity closure')
    wrappers=list(PATTERN.finditer(after_source))
    if len(wrappers)!=8 or len(list(PATTERN.finditer(after_header)))!=13:
        raise ValueError('Whole identity definition/caller closure missing')
    for match in wrappers:
        chosen,original=match[1],match[2]
        if chosen.startswith('SW_THREAD_LOCAL'):
            if chosen!='SW_THREAD_LOCAL swr_v1_coroutine_identity Coroutine::current = {nullptr};':
                raise ValueError('Current TLS/constant seed changed')
            continue
        inverse=chosen.replace('swr_v1_coroutine_identity_route(&current, &origin, this, SWR_CO_IDENTITY_ENTER);','origin = current;\n    current = this;')
        inverse=inverse.replace('swr_v1_coroutine_identity_route(&current, &origin, this, SWR_CO_IDENTITY_LEAVE);','current = origin;')
        inverse=inverse.replace('static_cast<CancelFunc *>(swr_v1_coroutine_identity_read(&cancel_fn_))','cancel_fn_')
        inverse=inverse.replace('swr_v1_coroutine_identity_read(&cancel_fn_)','cancel_fn_')
        inverse=inverse.replace('co->get_origin()','co->origin').replace('get_current()','current').replace('get_origin()','origin').replace('get_task()','task')
        if inverse!=selected(original):raise ValueError('Native effects or fresh identity observations changed')
    chosen_source='\n'.join(match[1] for match in wrappers)
    if any(token in chosen_source for token in ['!!task ', '*cancel_fn_;','co->origin','origin = current','current = origin']):
        raise ValueError('Native identity mirror/control remains')
    for old,new in [('static SW_THREAD_LOCAL Coroutine *current;','static SW_THREAD_LOCAL swr_v1_coroutine_identity current;'),('void *task = nullptr;','swr_v1_coroutine_identity task = {nullptr};'),('Coroutine *origin = nullptr;','swr_v1_coroutine_identity origin = {nullptr};'),('CancelFunc *cancel_fn_ = nullptr;','swr_v1_coroutine_identity cancel_fn_ = {nullptr};')]:
        if not any(m[1]==new and m[2]==old for m in PATTERN.finditer(after_header)):
            raise ValueError('Identity constant seed/name/type closure missing')
    cancel=block(chosen_source,'bool Coroutine::cancel()')
    previous=-1
    for effect in ['SWR_CO_STATUS_DECIDE','auto fn = *static_cast<CancelFunc *>','set_cancel_fn(nullptr)','SWR_CO_STATUS_PUBLISH','return fn(this)']:
        previous=cancel.index(effect,previous+1)
    return dict(source_closure=True,header_closure=True,native_effects_byte_equal_after_identity_inverse=True,
                pointer_cells=4,current_constant_native_TLS_seed=True,runtime_executed=False)
