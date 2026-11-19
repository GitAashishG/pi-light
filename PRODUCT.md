# How pi-light works

The [OMP extension](extension/index.ts) publishes each top-level session’s state to a [local bridge](host/bridge.py). The bridge combines the active sessions into one state and sends it over USB serial to the original Particle Photon. The [firmware](firmware/src/) drives the onboard RGB LED. The [printed enclosure](docs/ENCLOSURE.md) is optional.

## Session state

A run starts in `working`. A structured question, tool approval, or plan review sets `waiting` until all outstanding requests for that session have been resolved. Free-form text and time spent waiting for a model response do not trigger the amber light.

An agent end event with `willContinue: true` leaves the session working. A terminal event sets `done` on success, `error` on a run error, or `idle` on abort. A failed tool call does not turn the light red if the run continues. An outstanding question or review still takes priority.

## Multiple sessions and disconnects

The bridge selects the highest-priority state: `waiting`, `error`, `working`, `done`, then `idle`. Each extension renews its session lease every three seconds. Shutdown removes the session; a crashed publisher’s lease expires after twelve seconds. With no remaining sessions, the bridge sends `idle`.

The Photon has its own watchdog. If it stays powered but receives no valid state command for fifteen seconds, it switches to a slow dim-white pulse. A diagnostic query does not reset that timer. The next valid state command restores normal operation.

## Data flow

The extension sends an opaque session ID, sequence number, and state over a user-private Unix socket. The Photon receives only the aggregate state, sequence number, and brightness. It does not receive session IDs, prompts, tool arguments, or code. Neither the bridge nor the board needs a network connection during use.

See the [protocol reference](PROTOCOL.md) for message formats and the [README](README.md) to build and install pi-light.
