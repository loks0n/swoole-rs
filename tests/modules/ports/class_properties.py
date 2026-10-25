#!/usr/bin/env python3
"""Exact immutable PHP Port property declarations over inert Zend sinks; no Zend/runtime/lifetime effects."""
from pathlib import Path
import sys
from count import main

def extract(text,signature):
    start=text.index('void php_swoole_server_port_minit(')
    a=text.index('    for (size_t i = 0;; i++) {',start)if'swr_v1_ports_class_property(i)'in text else text.index('    zend_declare_property_null(swoole_server_port_ce, ZEND_STRL("onConnect")',start)
    end=text.index('\n}',a)
    return 'static void declare_properties() {\n'+text[a:end]+'\n}\n'

if __name__=='__main__':
    sys.exit(main(signatures=['class properties'],witness=Path(__file__).with_suffix('.cc'),scope=__doc__,source_path='ext-src/swoole_server_port.cc',body_extractor=extract))
