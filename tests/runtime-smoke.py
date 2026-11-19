#!/usr/bin/env python3
"""Exercise actual OMP hooks using a local deterministic provider, never a paid model."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from host.bridge import request


def until(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.05)
    raise AssertionError('Expected runtime state did not arrive before the bounded deadline')


class Runtime:
    def __init__(self, kind, state_dir, artifacts, extension):
        self.frames = queue.Queue()
        self.all_frames = []
        self.pending = []
        self.artifacts = artifacts
        self.kind = kind
        self.counter = 0
        self.log = (artifacts / (kind + '.stderr.log')).open('w')
        agent_dir = artifacts / ('agent-' + kind)
        agent_dir.mkdir(exist_ok=True)
        env = {key: os.environ[key] for key in ('HOME','PATH','TMPDIR','LANG','LC_ALL') if key in os.environ}
        env.update(PI_CODING_AGENT_DIR=str(agent_dir), PI_LIGHT_STATE_DIR=str(state_dir),
                   PI_LIGHT_TEST_KIND=kind, PI_NO_TITLE='1', PI_LIGHT_TEST_PYTHON=sys.executable)
        self.process = subprocess.Popen([
            shutil.which('omp'), '--mode','rpc-ui','--no-session','--no-extensions',
            '-e',str(extension), '-e',str(ROOT/'tests/runtime-provider.ts'),
            '--model','pi-light-fixture/fixture','--no-lsp','--tools','ask,read,bash' if kind=='async' else 'ask,read',
            '--config',str(ROOT/'tests/runtime.yml'), '--max-time','60',
            *(['--approval-mode','always-ask-cached'] if kind=='approval' else []),
            *(['--config',str(ROOT/'tests/runtime-async.yml')] if kind=='async' else []),
        ], cwd=artifacts, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, text=True, bufsize=1)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        self.wait(lambda frame: frame.get('type')=='ready', 25)
        self.command('get_state')

    def read(self):
        for line in self.process.stdout:
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            self.all_frames.append(frame)
            self.frames.put(frame)
        self.frames.put({'type':'process_exit'})

    def send(self, value):
        self.process.stdin.write(json.dumps(value)+'\n')
        self.process.stdin.flush()

    def wait(self, predicate, timeout=15):
        for index, frame in enumerate(self.pending):
            if predicate(frame):
                return self.pending.pop(index)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                frame=self.frames.get(timeout=max(0.01,deadline-time.monotonic()))
            except queue.Empty:
                break
            if frame.get('type') in ('extension_error','process_exit'):
                raise AssertionError('Runtime failed: '+json.dumps(frame))
            if predicate(frame): return frame
            self.pending.append(frame)
        raise AssertionError('Expected OMP frame did not arrive; inspect the isolated fixture frame log')

    def command(self, kind, **fields):
        self.counter+=1
        identity='test-'+str(self.counter)
        self.send({'id':identity,'type':kind,**fields})
        result=self.wait(lambda frame: frame.get('type')=='response' and frame.get('id')==identity)
        if not result.get('success'):
            raise AssertionError('OMP command failed: '+json.dumps(result))
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try: self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        (self.artifacts / (self.kind + '.frames.json')).write_text(json.dumps(self.all_frames,indent=2))
        self.log.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-bridge', action='store_true', help='Use the real private bridge; test session states will briefly control its light')
    parser.add_argument('--installed', action='store_true', help='Load the actual installed user-level loader instead of the source entry')
    args=parser.parse_args()
    extension=Path.home()/'.omp/agent/extensions/pi-light.ts' if args.installed else ROOT/'extension/index.ts'
    assert extension.is_file(), 'Indicator extension entry is missing'
    artifacts=ROOT/'.local/runtime-smoke'
    artifacts.mkdir(parents=True,exist_ok=True)
    (artifacts/'test-read.txt').write_text('Harmless isolated read approval test.\n')
    state_dir=Path.home()/'.local/state/pi-light' if args.live_bridge else artifacts/'state'
    bridge=None
    sessions=[]
    try:
        if not args.live_bridge:
            bridge=subprocess.Popen([sys.executable,str(ROOT/'host/bridge.py'),'serve','--state-dir',str(state_dir)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def status():
            try: return request(state_dir,{'op':'status'})
            except (OSError,ValueError): return None
        until(status)
        def aggregate(expected):
            def matches():
                value=status()
                if not value or value.get('aggregate')!=expected:
                    return None
                if args.live_bridge:
                    device=value.get('device',{})
                    if not device.get('connected') or device.get('state')!=expected:
                        return None
                return value
            return until(matches)

        busy=Runtime('hold',state_dir,artifacts,extension); sessions.append(busy)
        busy.command('prompt',message='Run the local held fixture only.')
        aggregate('working')
        question=Runtime('question',state_dir,artifacts,extension); sessions.append(question)
        question.command('prompt',message='Run the harmless question fixture only.')
        dialog=question.wait(lambda frame: frame.get('type')=='extension_ui_request' and frame.get('method')=='select')
        waiting=aggregate('waiting')
        assert waiting['sessions']>=2
        question.send({'type':'extension_ui_response','id':dialog['id'],'value':'Continue test'})
        question.wait(lambda frame: frame.get('type')=='agent_end' and not frame.get('willContinue') and frame.get('isTerminal',True))
        aggregate('working')
        busy.command('prompt',message='/fixture-release')
        busy.wait(lambda frame: frame.get('type')=='agent_end' and frame.get('isTerminal',True))
        done=aggregate('done')
        question.close(); sessions.remove(question)
        busy.close(); sessions.remove(busy)
        aggregate('idle')
        approval=Runtime('approval',state_dir,artifacts,extension); sessions.append(approval)
        approval.command('prompt',message='Run the harmless read-approval fixture only.')
        permission=approval.wait(lambda frame: frame.get('type')=='extension_ui_request' and frame.get('method')=='select')
        aggregate('waiting')
        # Refuse the isolated test action; the light never approves anything.
        assert 'Deny' in permission.get('options',[]), 'Approval prompt must offer an explicit deny choice'
        approval.send({'type':'extension_ui_response','id':permission['id'],'value':'Deny'})
        approval.wait(lambda frame: frame.get('type')=='agent_end' and frame.get('isTerminal',True))
        aggregate('done')
        approval.close(); sessions.remove(approval)
        aggregate('idle')
        failed=Runtime('error',state_dir,artifacts,extension); sessions.append(failed)
        failed.command('prompt',message='Run the intentional local error fixture only.')
        failed.wait(lambda frame: frame.get('type')=='agent_end' and frame.get('isTerminal',True))
        error=aggregate('error')
        failed.close(); sessions.remove(failed)
        aggregate('idle')
        evidence={'real_omp_runtime':True,'model_requests':'local fixture only; no external model',
                  'question_waiting':True,'two_session_precedence':True,'terminal_completion':True,
                  'unrecovered_error':True,'shutdown_cleanup':True,'live_bridge':args.live_bridge,
                  'installed_loader':args.installed,'denied_tool_approval_observed':True,
                  'states':{'waiting':waiting,'done':done,'error':error}}
        (artifacts/'result.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence,indent=2))
    finally:
        for session in sessions: session.close()
        if bridge:
            try: request(state_dir,{'op':'shutdown'})
            except Exception: pass
            try: bridge.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge.terminate(); bridge.wait(timeout=5)


if __name__=='__main__':
    main()
