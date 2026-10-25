#!/usr/bin/env python3
"""Exact EOF/length setter bodies over initialized native fields; bounded copying, no server or socket execution."""
from pathlib import Path
import sys
from count import main

if __name__=='__main__':
    sys.exit(main(
        signatures=['void ListenPort::set_eof_protocol(const std::string &eof, bool find_from_right)',
                    'void ListenPort::set_length_protocol(uint32_t length_offset, char length_type, uint32_t body_offset)',
                    'void ListenPort::set_stream_protocol()'],
        witness=Path(__file__).with_suffix('.cc'),scope=__doc__,
        support={'type-size.inc':('src/core/base.cc','int swoole_type_size(char type)'),
                 'stream.inc':('src/network/stream.cc','void Stream::set_protocol(Protocol *protocol)')}))
