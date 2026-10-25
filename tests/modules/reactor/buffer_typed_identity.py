"""Literal source/SDK identity for existing consumers under typed Buffer custody."""
import hashlib
import re
import owned_iov_identity as common
KEY='buffer_typed_requested'
MACRO='SWOOLE_RS_BUFFER_TYPED'
SOURCES=('crates/buffer/src/lib.rs','crates/buffer/src/typed.rs')
PATCHES=('migration/patches/buffer/0001-buffer-header.patch','migration/patches/buffer/0002-buffer-body.patch','migration/patches/reactor/0004-socket-output.patch')
OPERATIONS=('create','push','front','consume','pop')
CONSTRUCTOR='_ZN6swoole6BufferC1Ej'
FRONT='_ZNK6swoole6Buffer11typed_frontEv'

def requested(inputs,selected):
    value=common.requested(inputs,selected,key=KEY,source=SOURCES[1])
    if selected and not {'buffer','reactor'}<=set(inputs.get('modules',[])):
        raise ValueError('Typed Buffer requires actual Buffer and Reactor modules')
    return value

def configured(text,selected):return common.configured(text,selected,macro=MACRO)

def prepared(inputs,files):
    for name in SOURCES:
        if inputs.get('rust_sources_sha256',{}).get(name)!=hashlib.sha256(files[name]).hexdigest():
            raise ValueError('Typed Buffer source closure differs: '+name)
    for name in PATCHES:
        rows=[row for row in inputs.get('patches',[]) if row.get('path')==name]
        if len(rows)!=1 or rows[0].get('sha256')!=hashlib.sha256(files[name]).hexdigest():
            raise ValueError('Typed Buffer caller overlay differs: '+name)
    for operation in OPERATIONS:
        symbol='swr_v1_buffer_typed_'+operation
        if ('fn '+symbol+'(').encode() not in files[SOURCES[1]]:
            raise ValueError('Typed Buffer operation missing: '+operation)
        if not re.search(rb'^\+[^/\n]*\b'+symbol.encode()+rb'\(',files[PATCHES[1]],re.M):
            raise ValueError('Typed Buffer real facade caller missing: '+operation)
    for operation in ('typed_front','typed_consume','typed_sendfile'):
        if not re.search(rb'^\+[^/\n]*\b'+operation.encode()+rb'\(',files[PATCHES[2]],re.M):
            raise ValueError('Typed Buffer actual Socket caller missing: '+operation)
    return {name:hashlib.sha256(content).hexdigest() for name,content in files.items()}

def consumer(result,undefined,extension,selected):
    imports={line.split()[-1].lstrip('_') for line in undefined.splitlines() if line.split()}
    if CONSTRUCTOR.lstrip('_') not in imports or result.get('buffer_constructor_image')!=extension:
        raise ValueError('Actual Buffer constructor import/origin differs')
    if result.get('typed_buffer_compiled')!=int(selected):
        raise ValueError('Typed Buffer consumer compilation differs from SDK')
    if selected:
        if FRONT.lstrip('_') not in imports or result.get('typed_buffer_front_image')!=extension:
            raise ValueError('Actual typed front import/origin differs')
        if any(result.get(('typed_buffer_front_image_rust' if op=='front' else 'typed_buffer_'+op+'_image'))!=extension for op in OPERATIONS):
            raise ValueError('Typed Buffer actual Rust operation origins differ')
    elif FRONT.lstrip('_') in imports or any(result.get(('typed_buffer_front_image_rust' if op=='front' else 'typed_buffer_'+op+'_image')) is not None for op in OPERATIONS):
        raise ValueError('Native control imported/identified typed Buffer operations')
