"""Identity only for the unchanged supported readiness consumer's registry owner."""
import owned_iov_identity as storage

KEY = 'reactor_sockets_owned_requested'
MACRO = 'SWOOLE_RS_REACTOR_SOCKETS_OWNED'
SOURCE = 'crates/reactor/src/sockets.rs'
LENGTH = 'swr_v1_reactor_sockets_len'
POLICY = 'swr_v1_reactor_sockets_policy'


def requested(inputs, selected):
    return storage.requested(inputs, selected, key=KEY, source=SOURCE)


def consumer(result, undefined, extension, selected):
    imports = {line.split()[-1].lstrip('_') for line in undefined.splitlines() if line.split()}
    if result.get('registry_owned_compiled') != int(selected):
        raise ValueError('Registry consumer capability differs from configured SDK')
    if result.get('registry_policy') != int(selected):
        raise ValueError('Registry policy must be qualified Apple=1, Native OFF=0')
    for symbol, key in ((LENGTH, 'registry_len_image'), (POLICY, 'registry_policy_image')):
        if selected:
            if symbol not in imports or result.get(key) != extension:
                raise ValueError('Actual registry import/origin missing: '+symbol)
        elif symbol in imports or result.get(key) is not None:
            raise ValueError('Native control imported selected registry: '+symbol)
