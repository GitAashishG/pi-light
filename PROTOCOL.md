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

The bridge listens at `~/.local/state/pi-light/bridge.sock` (socket mode `0600`, directory mode `0700`). Each connection carries one newline-delimited JSON request of at most 4096 bytes and one response. The bridge rejects unknown request fields and does not log request payloads.

- Update: `{"op":"update","session":"<opaque-id>","seq":1,"state":"working"}`. Session ASCII id 1..128 characters `[A-Za-z0-9._:-]`. Reject stale or duplicate sequence updates without refreshing lease. Response `{ "ok": true, "aggregate": "working", "sessions": 1 }`.
- Remove: `{"op":"remove","session":"<opaque-id>","seq":2}`. Remove only if sequence is newer than the last accepted update; keep a bounded short-lived tombstone so reordered older updates do not revive the removed session. Same aggregate response.
- Status: `{"op":"status"}` returns the aggregate, session count, and cached device record, for example `{"ok":true,"aggregate":"working","sessions":1,"device":{"connected":true,"id":"...","state":"working","rgb":[0,0,64],"last_ack_age_s":0}}`. Unknown device fields are null. A status request does not open a serial connection or change the light.
- Query: `{"op":"query"}` sends `PI1?` over the bridge's existing serial connection. Success returns a fresh device acknowledgment in the status response; a disconnection or timeout returns `{"ok":false,"error":"..."}`. A query neither refreshes the firmware heartbeat nor blocks other local session updates.
- Shutdown: `{"op":"shutdown"}` stops the bridge for the current user. It sends `idle` if possible, closes the serial connection, and cleans up its runtime files.

One bridge process manages the USB port. It reconnects when the Photon is plugged in, checks the firmware hello, correlates acknowledgments by sequence number, and coalesces state updates. The bridge supports up to 256 live sessions. A lock prevents two processes from binding the same runtime directory; the bridge rejects symlinks and paths owned by a different user.

Run `.venv/bin/python host/bridge.py serve` for foreground operation. Use `--state-dir PATH` for an isolated runtime directory. The OMP extension starts the bridge on demand if it cannot connect to the socket.

## OMP extension

The installer adds `~/.omp/agent/extensions/pi-light.ts`, a loader for [`extension/index.ts`](extension/index.ts). Only top-level sessions publish. Each has an opaque ID, an increasing sequence number, and a three-second heartbeat. Session switch or shutdown removes the old publisher.

| OMP event | Effect |
| --- | --- |
| `before_agent_start`, `agent_start` | Set the base state to `working`. |
| `tool_execution_start` / `tool_execution_end` for `ask` | Add or remove a pending question. |
| `tool_approval_requested` / `tool_approval_resolved` | Add or remove a pending approval. |
| `plan_review_requested` / `plan_review_resolved` | Add or remove a pending plan review. |
| `agent_end` with `willContinue: true` | Keep the current base state. |
| Terminal `agent_end` | Set `done`, `error`, or `idle` according to the final assistant stop reason. Pending requests still take precedence. |

Heartbeats repeat the current state without replaying the completion flashes. The extension observes events but never resolves approvals. If the bridge is unavailable, the OMP run continues.
