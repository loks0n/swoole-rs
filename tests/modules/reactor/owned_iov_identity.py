"""Import/origin checks for the Rust-owned IOVector storage consumer."""

CONSTRUCTOR = '_ZN6swoole7network8IOVectorC1EPK5ioveci'
DESTRUCTOR = '_ZN6swoole7network8IOVectorD1Ev'
LENGTH = 'swr_v1_reactor_iov_owned_length'


def imports(undefined):
    return {line.split()[-1].lstrip('_') for line in undefined.splitlines() if line.split()}


def consumer(result, undefined, extension, selected):
    imported = imports(undefined)
    if any(symbol.lstrip('_') not in imported for symbol in (CONSTRUCTOR, DESTRUCTOR)):
        raise ValueError('Addon must import actual production IOVector constructor/destructor')
    if any(result.get(key) != extension for key in ('iov_constructor_image', 'iov_destructor_image')):
        raise ValueError('Actual IOVector constructor/destructor origins differ')
    if result.get('iov_owned_compiled') != int(selected):
        raise ValueError('Consumer compiled reactor module differs from the engine')
    if selected and (LENGTH not in imported or result.get('iov_owned_length_image') != extension):
        raise ValueError('Actual inline Rust-owned length import/origin missing')
    if not selected and LENGTH in imported:
        raise ValueError('Native consumer imported Rust-owned length')
