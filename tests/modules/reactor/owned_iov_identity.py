"""Fail-closed identity checks for separately requested Reactor storage owners."""
import re

KEY = 'reactor_iov_owned_requested'
MACRO = 'SWOOLE_RS_REACTOR_IOV_OWNED'
SOURCE = 'crates/reactor/src/iov_owned.rs'
CONSTRUCTOR = '_ZN6swoole7network8IOVectorC1EPK5ioveci'
DESTRUCTOR = '_ZN6swoole7network8IOVectorD1Ev'
LENGTH = 'swr_v1_reactor_iov_owned_length'


def requested(inputs, selected, *, key=KEY, source=SOURCE):
    value = inputs.get(key, False)
    if type(value) is not bool or value is not selected:
        raise ValueError(key+': requires explicit selected request and Native request OFF')
    if selected and source not in inputs.get('rust_sources_sha256', {}):
        raise ValueError(source+': implementation missing from attested source closure')
    return value


def configured(text, selected, *, macro=MACRO):
    # Accept only a literal configured 0/1; duplicate/indirect values fail closed.
    values = re.findall(r'^\s*#\s*define\s+' + re.escape(macro) + r'\b([^\n]*)', text, re.M)
    undefs = re.findall(r'^\s*#\s*undef\s+' + re.escape(macro) + r'\b', text, re.M)
    if len(values) > 1 or (values and (undefs or values[0].strip() not in ('0', '1'))):
        raise ValueError(macro+': ambiguous SDK configuration')
    enabled = bool(values and values[0].strip() == '1')
    if enabled is not selected:
        raise ValueError(macro+': selected SDK must be ON and Native SDK OFF')
    return enabled


def consumer(result, undefined, extension, selected):
    imports = {line.split()[-1].lstrip('_') for line in undefined.splitlines() if line.split()}
    def imported(symbol):return symbol.lstrip('_') in imports
    if any(not imported(symbol) for symbol in (CONSTRUCTOR, DESTRUCTOR)):
        raise ValueError('Addon must import actual production IOVector constructor/destructor')
    if any(result.get(key) != extension for key in ('iov_constructor_image', 'iov_destructor_image')):
        raise ValueError('Actual IOVector constructor/destructor origins differ')
    if result.get('iov_owned_compiled') != int(selected):
        raise ValueError('Consumer compiled capability differs from configured SDK')
    if selected and (not imported(LENGTH) or result.get('iov_owned_length_image') != extension):
        raise ValueError('Actual inline Rust-owned length import/origin missing')
    if not selected and imported(LENGTH):
        raise ValueError('Native consumer imported Rust-owned length')
