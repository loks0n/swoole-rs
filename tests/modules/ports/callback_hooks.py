#!/usr/bin/env python3
"""Callback binding-selection models only; inert native slots, no callback execution or lifetime profiles."""
from pathlib import Path
import sys
from count import main
import overlay


def extract(text, signature):
    method=text.index('static PHP_METHOD(swoole_server_port, on) {')
    begin=text.index('    switch (swr_v1_ports_callback_hook(index))',method) if 'swr_v1_ports_callback_hook(index)'in text else text.index('        if (index == SW_SERVER_CB_onConnect',method)
    end=text.index('    RETURN_TRUE;',begin)
    if 'swr_v1_ports_callback_hook(index)'not in text:end=text.index('        break;',begin)
    return 'static void apply(Server *serv, int index) {\n'+text[begin:end]+'}\n'


def support(folder,args):
    raw=overlay.original('ext-src/php_swoole_server.h');a=raw.index('enum php_swoole_server_port_callback_type {');b=raw.index('};',a)+2
    data=(raw[a:b]+'\n').encode();(folder/'events.inc').write_bytes(data)
    return {}


if __name__=='__main__':
    sys.exit(main(signatures=['HOOK_BINDING'],witness=Path(__file__).with_suffix('.cc'),scope=__doc__,source_path='ext-src/swoole_server_port.cc',body_extractor=extract,extra_support=support))
