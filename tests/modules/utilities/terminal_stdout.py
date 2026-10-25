#!/usr/bin/env python3
"""Give an unchanged stdio-dependent original terminal stdout, preserving stderr."""
import errno
import os
import subprocess
import sys
import threading
import tty

master, slave = os.openpty()
tty.setraw(slave)


def relay():
    while True:
        try:
            data = os.read(master, 65536)
        except OSError as error:
            if error.errno == errno.EIO:
                return
            raise
        if not data:
            return
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


reader = threading.Thread(target=relay)
reader.start()
try:
    # Inherit the outer run_isolated process group, so its timeout/cleanup also
    # bounds this child and the original's fork. No new process group here.
    result = subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL, stdout=slave)
finally:
    os.close(slave)
reader.join()
os.close(master)
sys.exit(result.returncode)
