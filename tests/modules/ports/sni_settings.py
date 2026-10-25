#!/usr/bin/env python3
"""Valid initialized SNI frontend mapping models and pure admission plans; no matching/crypto/failure/lifetime/stopped execution."""
from pathlib import Path
import sys
from count import main,accessor
from tls_settings import support as tls_support


def extract(text,signature):
    if signature!='SNI_FRONTEND':return accessor(text,signature)
    method=text.index('static PHP_METHOD(swoole_server_port, set) {');marker='        // SNI frontend admission only; native iteration/context/crypto remains authoritative.'
    start=text.index(marker,method)if marker in text else text.index('        if (php_swoole_array_get_value(vht, "ssl_sni_certs", ztmp)) {',method)
    end=text.index('        if (!port->get_ssl_cert_file().empty() || !port->has_sni_contexts()) {',start)
    return 'static bool sni_prefix(SniPort *port, HashTable *vht) {\n    zval *ztmp = nullptr;\n'+text[start:end]+'    return true;\n}\n'


def support(folder,args):
    report=tls_support(folder,args)
    report.update({'scope':'Only valid stable native model mappings; context duplication/file/add outcomes are supplied successful effects, no matching/crypto/IO'})
    return report


if __name__=='__main__':
    sys.exit(main(signatures=['static bool php_swoole_server_set_ssl_option(', 'SNI_FRONTEND'],
                  witness=Path(__file__).with_suffix('.cc'),scope=__doc__,source_path='ext-src/swoole_server_port.cc',body_extractor=extract,extra_support=support))
