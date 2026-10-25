#!/usr/bin/env python3
"""Initialized successful event-init ordering models and pure candidate admission; no real reactor/runtime/callback/lifetime profiles."""
from pathlib import Path
import sys
import overlay
from response import main


def extract(text):
    begin=text.index('int swoole_event_init(');end=text.index('\n}\n',begin)+2
    return text[begin:end]+'\n'


def support(folder,args):
    text=overlay.original('include/swoole.h');begin=text.index('enum swEventInitFlag {');end=text.index('};',begin)+2;(folder/'flags.inc').write_text(text[begin:end]+'\n')
    return {'actual_native_reactor_or_user_callback_executed':False,'rejected_native_initialization_or_stopped_profile_executed':False}


if __name__=='__main__':
    sys.exit(main(scope=__doc__,witness=Path(__file__).with_suffix('.cc'),source_path='src/wrapper/event.cc',body_extractor=extract,support=support))
