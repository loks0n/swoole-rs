"""Whole CID/registration boundary source proof, never constructs a Coroutine."""
import re
from ordered_gate import block
from make_coroutine_creation import GUARD

PATTERN=re.compile(r'#if defined\(SWOOLE_RS_COROUTINE\) && SWOOLE_RS_COROUTINE // SWR_CREATION_BEGIN\n(.*?)\n#else // SWR_CREATION_NATIVE\n(.*?)\n#endif // SWR_CREATION_END',re.S)
REMOVE='    coroutines.erase(get_cid());'


def restore_creation(after_source,after_header):
    source=PATTERN.sub(lambda m:m[2],after_source).replace('#include <new>\n','',1)
    old=block(source,'long Coroutine::run()');new=old.replace('const long _cid = get_cid();','const long _cid = cid;');source=source.replace(old,new,1)
    old=block(source,'void Coroutine::close()');new=old.replace(REMOVE,'    coroutines.erase(cid);');source=source.replace(old,new,1)
    header=PATTERN.sub(lambda m:m[2],after_header).replace(GUARD,'',1)
    return source,header


def verify_creation(before_source,after_source,before_header,after_header):
    source,header=restore_creation(after_source,after_header)
    if source!=before_source or header!=before_header:
        raise ValueError('Unrelated bytes changed outside complete CID/creation closure')
    if len(list(PATTERN.finditer(after_source)))!=1 or len(list(PATTERN.finditer(after_header)))!=3:
        raise ValueError('Whole constructor/CID/getter/lookup wrapper closure missing')
    if after_header.count(GUARD)!=1:raise ValueError('CID long geometry guard missing')
    declaration=[m for m in PATTERN.finditer(after_header) if m[2]=='    long cid;']
    if len(declaration)!=1 or declaration[0][1]!='    swr_v1_coroutine_cid cid;':
        raise ValueError('CID needs exact same field name/position and no early initializer')
    ctor=block(after_source,'Coroutine::Coroutine(')
    previous=block(before_source,'Coroutine::Coroutine(')
    if ctor[:ctor.index('{')]!=previous[:previous.index('{')]:
        raise ValueError('Native Context construction order/arguments changed')
    if 'cid = ' in ctor or 'next_id(' in ctor or 'publish_peak(' in ctor:
        raise ValueError('Native scalar/creation policy mirror remains')
    if 'activate();\n            return;' not in ctor:
        raise ValueError('Activation must be terminal, no later object/Rust observation')
    if 'case SWR_CO_CREATE_ALLOCATION:\n            throw std::bad_alloc();' not in ctor:
        raise ValueError('Rust allocation refusal must return to Native exception boundary')
    run=block(after_source,'long Coroutine::run()');last=-1
    for text in ['const long _cid = get_cid()','identity_route','CALC_EXECUTE_USEC','status_transition','ctx.swap_in()','check_end()','return _cid']:
        last=run.index(text,last+1)
    close=block(after_source,'void Coroutine::close()');last=-1
    for text in ['dispatch.function(dispatch.task)','swoole_trace_log','identity_route',REMOVE,'delete this']:
        last=close.index(text,last+1)
    if close[close.index('delete this;')+len('delete this;'):].strip()!='}':
        raise ValueError('Post-delete object/Rust access added')
    return dict(source_closure=True,header_closure=True,context_constructor_precedes_CID=True,
                CID_uninitialized_until_body_raw_publication=True,activation_terminal=True,
                original_exceptions_no_added_rollback=True,predelete_CID_snapshot=True,
                runtime_executed=False)
