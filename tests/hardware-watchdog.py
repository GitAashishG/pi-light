#!/usr/bin/env python3
"""Real Photon integration test. Stop the bridge first; this briefly controls its LED."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

import serial
from serial.tools import list_ports

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.bridge import request
from host.transport import Frames, parse_ack, parse_hello

from host.model import RequestError
STATE_DIR=Path.home()/'.local/state/pi-light'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id',required=True,help='24-hex ID of the exact Photon to test')
    args=parser.parse_args()
    identity=args.device_id.lower()
    if not re.fullmatch(r'[0-9a-f]{24}',identity):
        parser.error('--device-id must contain exactly 24 hexadecimal characters')
    try:
        request(STATE_DIR,{'op':'status'})
    except (OSError,ValueError,RequestError):
        pass
    else:
        raise SystemExit('Stop the bridge before running the exclusive hardware test.')
    ports=[p.device for p in list_ports.comports() if p.vid==0x2b04 and p.pid==0xc006 and p.serial_number==identity]
    if len(ports)!=1:
        raise SystemExit('The exact admitted Photon serial interface is not uniquely available.')
    frames=Frames()
    sequence=0
    with serial.Serial(ports[0],115200,timeout=.1,write_timeout=.5,exclusive=True) as device:
        def receive(parser, expected=None):
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                for line in frames.feed(device.read(96)):
                    value=parser(line)
                    if value is not None and (expected is None or value[0]==expected):
                        return value
            raise AssertionError('No matching actual device acknowledgment before deadline')
        def query():
            nonlocal sequence
            sequence+=1
            device.write(f'PI1? {sequence}\n'.encode())
            return receive(parse_ack,sequence)
        device.write(b'HELLO\n')
        assert receive(parse_hello)==identity
        sequence+=1
        device.write(f'PI1 {sequence} working 48\n'.encode())
        assert receive(parse_ack,sequence)[1]=='working'
        start=time.monotonic()
        became_offline=None
        # This deliberately exercises the MCU's physical 15s watchdog. A fake
        # host timer cannot prove its independence from host process failure.
        while time.monotonic()-start<20:
            ack=query()
            if ack[1]=='offline':
                became_offline=time.monotonic()-start
                break
            assert ack[1]=='working'
            device.write(b'not-a-valid-command\nHELLO\n')
            time.sleep(.25)
        assert became_offline is not None and became_offline>=14
        sequence+=1
        device.write(f'PI1 {sequence} done 48\n'.encode())
        assert receive(parse_ack,sequence)[1]=='done'
        # Observe the real completion transition until it must be latched.
        done_at=time.monotonic()
        while time.monotonic()-done_at<3.2:
            query()
            time.sleep(.1)
        before=query()
        assert before[1]=='done' and before[2][1]>0 and before[2][0]==before[2][2]==0
        sequence+=1
        device.write(f'PI1 {sequence} done 48\n'.encode())
        repeated=receive(parse_ack,sequence)
        assert repeated[1]=='done' and repeated[2]==before[2]
        sequence+=1
        device.write(f'PI1 {sequence} idle 48\n'.encode())
        final=receive(parse_ack,sequence)
        assert final[1]=='idle'
        evidence={'real_device':identity,'offline_after_s':round(became_offline,3),
                  'queries_hello_and_invalid_input_did_not_renew_heartbeat':True,
                  'completion_latched_through_repeated_state':True,'final_ack':final}
        (ROOT/'.local/hardware-watchdog.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence,indent=2))


if __name__=='__main__':
    main()
