#!/usr/bin/env python3
"""Exact Port constructor body defaults; native POD fields and literal copying, no IO or fault injection."""
from pathlib import Path
import sys
from count import main

if __name__=='__main__':
    sys.exit(main(signatures=['ListenPort::ListenPort(Server *server)'],
                  witness=Path(__file__).with_suffix('.cc'),scope=__doc__,
                  support={'config.inc':('include/swoole_config.h',None)}))
