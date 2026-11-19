# pi-light interfaces, version 1

## States and priorities

Canonical host states: `working`, `waiting`, `done`, `error`, `idle`. The board also has a derived `offline` state when no valid command has arrived for 15,000 ms. Priority among unexpired session leases: waiting > error > working > done > idle. Empty bridge session set means idle. Session heartbeats every 3 s; lease TTL 12 s. Sequence numbers are unsigned 32-bit on USB and nonnegative safe integers per publisher on the local socket. Host leases use monotonic time only.

## Photon USB serial, 115200 baud

The device announces `PI-LIGHT 1 <device-id>` followed by newline when serial connects or a hello query arrives. A hello request is exactly `HELLO\n` and refreshes no state heartbeat. Target the actual original Photon by its USB identity; do not open unrelated serial devices. Use this handshake before any state command.

Commands:

- `PI1 <sequence> <state> <brightness>\n`: state is one of the canonical five, brightness 0..128. Apply the state and refresh the device heartbeat. Reply `PI1 <sequence> <effective-state> <red> <green> <blue>\n` using currently applied RGB channel values 0..255.
- `PI1? <sequence>\n`: query without refreshing heartbeat. Same reply format, including `offline` if the deadline elapsed.

The host sends the current aggregate state at least every 3 s, default brightness 48. Malformed or oversized lines return `ERR invalid-command` and do not refresh the heartbeat or alter state. Max physical line is 96 bytes including newline. Parse with fixed-size storage, bounded input per loop, no dynamic allocation in animation/serial hot paths. Sequence IDs correlate replies; duplicate state heartbeats must not restart completion flashes. USB unplug/crashed host causes offline white, not a lingering success signal. Use monotonic unsigned millis deltas across wrap.

Visual defaults: working slow blue breath; waiting amber pulse at no more than 2Hz; done green pulses on transition then steady; error a distinct red pulse pattern; idle very dim steady white; offline a slow dim-white breathing pattern distinct from idle. No delays that stall USB handling. Wi-Fi and Particle cloud remain off. Board firmware controls the RGB LED directly; built-in boot/DFU status is not a pi-light state.

## Local Unix socket

Default state directory: `~/.local/state/pi-light`, mode0700. Socket: `bridge.sock`, mode0600. Bridge lock and PID metadata live in the same private directory. No TCP listener and no filesystem secrets. JSONL request/response, max4096 bytes per request. Each request gets one JSON response before connection close. The bridge accepts only the schema keys for the operation and does not log request payloads.

- Update: `{"op":"update","session":"<opaque-id>","seq":1,"state":"working"}`. Session ASCII id 1..128 characters `[A-Za-z0-9._:-]`. Reject stale or duplicate sequence updates without refreshing lease. Response `{ "ok": true, "aggregate": "working", "sessions": 1 }`.
- Remove: `{"op":"remove","session":"<opaque-id>","seq":2}`. Remove only if sequence is newer than the last accepted update; keep a bounded short-lived tombstone so reordered older updates do not revive the removed session. Same aggregate response.
- Status: `{"op":"status"}` returns `{ "ok":true, "aggregate":"...", "sessions":0, "device":{"connected":true,"id":"...","state":"...","rgb":[0,0,0],"last_ack_age_s":0} }`. Missing/unknown device fields are null; never fabricate a connected device. Status must not open another serial connection or override aggregate state.
- Query: `{"op":"query"}` uses the single serial owner to send `PI1?` without refreshing the firmware heartbeat. Return the normal status shape with freshly queried device fields on success, or `{"ok":false,"error":"..."}` with a fixed error if disconnected or the bounded query deadline expires. Other local updates/status requests continue while a query waits; never return stale cached data as a successful query.
- Shutdown: `{"op":"shutdown"}` stops only this user's bridge, sends idle if possible, closes resources and unlinks owned socket/lock metadata. No other session/process/service is touched.

The bridge handles one serial owner, reconnects when the Photon is plugged back in, validates hello/ACK frames, coalesces updates, and refreshes aggregate/lease expiration even when no events arrive. USB failures never block local socket replies or OMP handlers. Bound open/read/write waits and request sizes. Max256 live sessions, bounded tombstones, fixed benign error strings. Invalid clients cannot escape the current user's socket permissions. Do not unlink a live socket owned by another instance; use a lock, reject symlinked/unowned paths, and leave unrelated files alone.

Bridge entry point: `.venv/bin/python host/bridge.py serve` (foreground), with optional `--state-dir PATH` for isolated tests. `host/bridge.py status` and `stop` speak the socket protocol. The OMP extension may autostart `serve` as a detached process with a minimal environment, relying on the bridge lock to prevent duplicate owners. User-facing diagnostics can select a Photon port explicitly but must still require the firmware handshake.

## OMP extension

Project entry `extension/index.ts`, installed as a small user-level loader `~/.omp/agent/extensions/pi-light.ts`. Use public ExtensionAPI only; do not change managed extensions, config.yml, models, permissions or approval behavior. Top-level sessions only (`ctx.agent.kind === main`). Opaque publisher ID per root session instance; handle session switches/removal and shutdown without cross-session globals. Managed context timers provide 3-second heartbeats and safe cleanup. Local socket publication is asynchronous, bounded and failure-isolated, with per-session monotonic sequence numbers.

Actual hooks: agent_start/before_agent_start -> working; tool_execution_start/end for ask -> add/remove a keyed waiting reason; tool_approval_requested/resolved and plan_review_requested/resolved -> keyed waiting reasons. Do not forward event content. `agent_end.willContinue === true` is nonterminal and must not become done. Terminal agent_end (or a safely settled supported signal) can produce done/error/idle after pending waits clear; use final assistant stopReason metadata only to distinguish an unrecovered error or user abort, without inspecting text. Keep a main run with async work active until its actual terminal signal. Session shutdown/switch removes old publisher. No approval resolution APIs may be called.

Error and complete states latch until a new run/closure; a heartbeat repeats state, never replays green transition animation. The extension's transport errors do not throw into OMP. Do not use global raw timers with unhandled callbacks; use ctx-managed timers and safe bounded callback code. Fail closed on unexpected payloads but do not alter agent execution.
