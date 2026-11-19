#!/usr/bin/env python3
"""Finite real background process used only by the async-yield acceptance test."""
from pathlib import Path
import time

Path('async.ready').write_text('owned worker started\n')
deadline=time.monotonic()+40
while not Path('async.release').exists():
    if time.monotonic()>=deadline:
        raise SystemExit('Fixture release was not received before the finite deadline')
    time.sleep(.05)
Path('async.completed').write_text('owned worker released and completed\n')
print('The owned pi-light background fixture completed.')
