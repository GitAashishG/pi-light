#!/usr/bin/env python3
"""Regress real async-job yields through OMP, the installed loader and optional Photon."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.bridge import request
from host.model import RequestError

spec=importlib.util.spec_from_file_location('pi_light_runtime_smoke',ROOT/'tests/runtime-smoke.py')
smoke=importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-bridge',action='store_true',help='Require actual device acknowledgments through the normal bridge')
    args=parser.parse_args()
    artifacts=ROOT/'.local/async-runtime'
    artifacts.mkdir(parents=True,exist_ok=True)
    for name in ('async.ready','async.release','async.completed'):
        (artifacts/name).unlink(missing_ok=True)
    state_dir=Path.home()/'.local/state/pi-light' if args.live_bridge else artifacts/'state'
    bridge=None
    runtime=None
    try:
        if not args.live_bridge:
            bridge=subprocess.Popen([sys.executable,str(ROOT/'host/bridge.py'),'serve','--state-dir',str(state_dir)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def status():
            try: return request(state_dir,{'op':'status'})
            except (OSError,ValueError,RequestError): return None
        initial=smoke.until(status)
        assert initial['sessions']==0,'Run without other publishers so this regression cannot hide behind another session'
        if args.live_bridge:
            assert initial['device']['connected'],'Live test requires the admitted Photon'
        installed=Path.home()/'.omp/agent/extensions/pi-light.ts'
        runtime=smoke.Runtime('async',state_dir,artifacts,installed)
        runtime.command('prompt',message='Start the owned async worker and yield until its real completion arrives.')
        paused=runtime.wait(lambda frame: frame.get('type')=='agent_end' and frame.get('isTerminal') is False,timeout=20)
        observed=runtime.wait(lambda frame: frame.get('type')=='pi_light_test_extension_end' and frame.get('willContinue') is True)
        smoke.until(lambda: (artifacts/'async.ready').is_file(),seconds=5)
        assert not (artifacts/'async.completed').exists(),'Worker completed before yield was checked'
        running=runtime.command('get_state')['data']
        assert running.get('hasPendingAsyncWork') is True and running.get('isSettled') is False
        def working():
            value=status()
            if not value or value['aggregate']!='working': return None
            if args.live_bridge and (not value['device']['connected'] or value['device']['state']!='working'): return None
            return value
        blue=smoke.until(working)
        # External OMP and its managed 3s heartbeats use real clocks. Observe a
        # complete heartbeat interval while the real worker is still held open.
        guard_deadline=time.monotonic()+3.2
        samples=0
        while time.monotonic()<guard_deadline:
            value=status()
            assert value and value['aggregate']=='working','False completion while an owned async worker was pending'
            if args.live_bridge:
                assert value['device']['connected'] and value['device']['state']=='working'
            assert not (artifacts/'async.completed').exists()
            assert not any(frame.get('type')=='session_settled' for frame in runtime.all_frames)
            samples+=1
            time.sleep(.05)
        (artifacts/'async.release').write_text('release the owned test worker\n')
        settled=runtime.wait(lambda frame: frame.get('type')=='session_settled',timeout=15)
        assert (artifacts/'async.completed').is_file(),'Settlement must follow actual process completion'
        final_event=runtime.wait(lambda frame: frame.get('type')=='pi_light_test_extension_end' and frame.get('willContinue') is not True)
        final_state=runtime.command('get_state')['data']
        assert final_state.get('isSettled') is True and final_state.get('hasPendingAsyncWork') is False
        def complete():
            value=status()
            if not value or value['aggregate']!='done': return None
            if args.live_bridge and (not value['device']['connected'] or value['device']['state']!='done'): return None
            return value
        green=smoke.until(complete)
        async_starts=[frame for frame in runtime.all_frames if frame.get('type')=='tool_execution_end' and frame.get('toolName')=='bash']
        assert any(frame.get('result',{}).get('details',{}).get('async',{}).get('state')=='running' for frame in async_starts),'Native bash did not actually background the command'
        evidence={'real_omp_runtime':True,'installed_loader':True,'real_background_bash_job':True,
                  'external_model_requests':False,'live_photon':args.live_bridge,
                  'wire_nonterminal':{key:paused.get(key) for key in ('type','isTerminal','awaitingAsyncWork','yielded')},
                  'extension_nonterminal':observed,'state_during_yield':blue,
                  'pending_observation_samples':samples,'extension_terminal':final_event,
                  'state_after_worker_and_settlement':green,'session_settled':settled.get('type')=='session_settled',
                  'production_handler_changed':False}
        (artifacts/'result.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence,indent=2))
    finally:
        # Releases only this finite fixture; session disposal owns any job cleanup.
        (artifacts/'async.release').touch()
        if runtime: runtime.close()
        if bridge:
            try: request(state_dir,{'op':'shutdown'})
            except (OSError,ValueError,RequestError): pass
            try: bridge.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge.terminate();bridge.wait(timeout=5)


if __name__=='__main__':
    main()
