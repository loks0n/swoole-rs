#!/usr/bin/env python3
"""Normal lazy option order/alias/default/conversion catalog; valid prefix only, no callbacks/reentry/fatal/stopped profiles."""
from pathlib import Path
import sys
from flags import run

if __name__=='__main__':
    sys.exit(run(Path(__file__).with_suffix('.cc'),__doc__))
