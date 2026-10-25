#!/usr/bin/env python3
"""Normal non-TLS settings prefix plus pure packet plans; no original over-capacity copies, native fatal or stopped profiles."""
from pathlib import Path
import sys
from flags import run

if __name__=='__main__':
    sys.exit(run(Path(__file__).with_suffix('.cc'),__doc__))
