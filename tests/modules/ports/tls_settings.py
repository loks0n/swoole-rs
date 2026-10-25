#!/usr/bin/env python3
"""Successful TLS frontend call-order models and scalar metadata; no crypto/filesystem/failure/SNI/lifetime/stopped execution."""
from pathlib import Path
import sys
import overlay
from count import main,accessor


def extract(text,signature):
    if signature!='TLS_PORT_OPTIONS':return accessor(text,signature)
    method=text.index('static PHP_METHOD(swoole_server_port, set) {')
    marker='        // TLS frontend order/conversion only; SNI and crypto algorithms remain native.'
    start=text.index(marker,method)if marker in text else text.index('        if (php_swoole_array_get_value(vht, "ssl_compress", ztmp)) {',method)
    boundary='        // SNI frontend admission only; native iteration/context/crypto remains authoritative.'
    end=text.index(boundary,start)if boundary in text else text.index('        if (php_swoole_array_get_value(vht, "ssl_sni_certs", ztmp)) {',start)
    return 'static void tls_prefix(TlsPort *port, HashTable *vht) {\n    zval *ztmp = nullptr;\n'+text[start:end]+'}\n'


def support(folder,args):
    raw=overlay.original('include/swoole.h');p=folder/'bounds.inc';p.write_text('\n'.join(line for line in raw.splitlines()if line.startswith(('#define SW_MAX(', '#define SW_MIN(')))+'\n')
    return {'scope':'Only pinned bound macros; native TLS/filesystem outcomes are supplied as successful facts'}


if __name__=='__main__':
    sys.exit(main(signatures=['static bool php_swoole_server_set_ssl_option(', 'TLS_PORT_OPTIONS'],
                  witness=Path(__file__).with_suffix('.cc'),scope=__doc__,source_path='ext-src/swoole_server_port.cc',body_extractor=extract,extra_support=support))
