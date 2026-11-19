# Operating pi-light

Use the [README installation steps](../README.md#3-install-the-host-integration) for the host setup and [Build and flash the Photon](FIRMWARE.md) for firmware installation or recovery. Run the commands below from the repository root with the host dependencies installed. If `pi-light` is not on `PATH`, use `~/.local/bin/pi-light`.

## Bridge lifecycle

New default-profile OMP sessions load the installed extension. Restart or reload existing sessions to pick it up. A publisher connection failure can start the bridge as a detached process; it is not a login service. Diagnostics do not start it.

To run it in a foreground terminal:

```sh
pi-light serve
```

Only one bridge can use a runtime directory and its USB connection. Before flashing, opening a serial monitor, or changing bridge startup settings, close OMP sessions using pi-light and stop manual publishers, then run:

```sh
pi-light stop
```

Allow the bridge to exit and release USB before continuing. A live publisher can restart it on its next heartbeat, including an idle OMP session. Graceful shutdown sends idle when possible; a disconnected or unresponsive device may not receive that final state. See the [brightness instructions](../README.md#brightness-and-stopping) for startup-only brightness configuration.

## State diagnostics

```sh
pi-light status
pi-light query
```

`status` reports the desired aggregate and cached device feedback. `query` requests a fresh acknowledgment through the existing serial connection and fails if the device is unavailable or times out. Neither command changes the aggregate state.

| Field | Meaning |
| --- | --- |
| `aggregate` | Desired state from unexpired publishers, or `idle` when none remain. It does not establish a USB connection. |
| `sessions` | Number of live publisher leases, including idle sessions. |
| `device.connected` | Whether the bridge has completed the pi-light handshake and has not detected a subsequent transport failure. |
| `device.id` | Identity returned by the firmware handshake. Redact it before sharing diagnostics. |
| `device.state`, `device.rgb` | Last acknowledged state and PWM-register-derived RGB channels, not an optical measurement. |
| `device.last_ack_age_s` | Age of the last acknowledgment. A successful `query` supplies fresh feedback. |

Unknown device fields are `null`. After disconnection, cached identity and acknowledgment fields can remain populated; check `connected` and acknowledgment age rather than reading a cached green state as current success. An animation's RGB values vary over time, and brightness 0 makes every pattern dark.

Publishers refresh every three seconds and expire after twelve seconds without an update. The bridge sends the current aggregate to the Photon every three seconds, even when there are no publishers. The firmware independently enters `offline` after fifteen seconds without a valid state command. Queries, `HELLO`, and invalid frames do not renew that timer, but querying a running bridge does not stop its normal state heartbeats. Removing all publishers therefore tests lease cleanup to idle, not the firmware watchdog.

For state precedence and frame formats, see [PROTOCOL.md](../PROTOCOL.md). Use the [manual light test](../README.md#manual-light-test) to exercise a short-lived publisher without bypassing normal priorities. Duplicate or older publisher sequence numbers return `stale-sequence`; use a fresh opaque session ID or increase the sequence.

## USB and macOS troubleshooting

The runtime needs an original Photon running pi-light, a data-capable USB cable, and an accessible normal-mode USB serial interface. Automatic discovery accepts exactly one candidate with VID/PID `2b04:c006`, then requires the `PI-LIGHT 1 <device-id>` handshake. A Photon in DFU (`2b04:d006`) or listening mode is not ready for normal indicator use.

List serial interfaces without opening them:

```sh
.venv/bin/python -m serial.tools.list_ports -v
```

| Symptom | Action |
| --- | --- |
| `bridge-unavailable` | Start a newly loaded OMP session or run `pi-light serve`. Check that the checkout, `.venv`, and installed loader still exist. |
| `serial-dependency-unavailable` | Install the pinned host dependency using the [README prerequisites and setup](../README.md#prerequisites). |
| `device-unavailable`, `device-timeout`, or `connected: false` | Check the data cable, firmware mode and handshake. Close serial monitors and disconnect other Photons so automatic selection is unambiguous. |
| macOS reports transport restrictions or the USB interface remains inaccessible | Unlock the Mac and respond to its native accessory prompt for the intended Photon. Re-enumeration after flashing can require another prompt. Do not disable accessory protection, change global permissions, or weaken screen-lock policy. |
| `already-running` | Another bridge is active in that runtime directory. Close publishers and stop it before changing startup settings. |
| Safe-mode, listening or DFU colors | Inspect module compatibility and follow the [firmware recovery guide](FIRMWARE.md#4-choose-the-appropriate-flash-path). Device OS colors are not pi-light states. |

For an explicit-port diagnosis, stop the existing bridge first, identify the exact Photon port from local enumeration, set `PHOTON_PORT` to that path, then run:

```sh
pi-light serve --port "$PHOTON_PORT"
```

Explicit selection still requires the pi-light handshake. Never guess a port or point it at unrelated hardware. Device identity must be checked again after USB mode changes; the port path can change.

Firmware upgrades need a stable power source and may have intermediate states where pi-light cannot run. A bootloader update interrupted by power loss can require hardware recovery; DFU is not a general bootloader repair mechanism. Use the [flash guide's dependency checks and recovery paths](FIRMWARE.md#3-identify-the-board-and-inspect-its-dependencies), not raw address writes, mass erase, factory reset, or configuration/key-region writes.

## Runtime files and privacy

The default runtime directory is `~/.local/state/pi-light`, mode 0700, with a mode-0600 `bridge.sock` and private `bridge.lock` PID metadata. The bridge locks the directory, rejects symlinked or unowned runtime resources, and cleans up its own socket and metadata on exit. An `unsafe-state-path` error is a reason to inspect filesystem ownership, permissions and symlinks, not to loosen permissions or delete a live socket.

The extension publishes only opaque identity, state and sequence numbers. The device receives only aggregate state, sequence and brightness. Prompts, source code, tool arguments and credentials are not part of either interface. Keep diagnostic output containing device identifiers private or redact it before sharing.

## Functional checks

After firmware inspection passes, start the bridge and require a successful fresh `query` with `device.connected: true`. Use the README's manual publisher test to compare the visible LED with acknowledged state. Verify that repeated `done` updates preserve steady green after the initial three flashes, and that publisher removal or lease expiry returns the aggregate to idle when no other publisher remains.

Optional end-to-end fixtures use a deterministic local provider rather than a paid model. They require OMP, the installed loader, a running normal bridge and a connected Photon. Close all other publishers first; these commands briefly control the light:

```sh
.venv/bin/python tests/runtime-smoke.py --installed --live-bridge
.venv/bin/python tests/async-runtime.py --live-bridge
```

The first fixture checks waiting, completion, run errors, multi-session priority and shutdown cleanup. The second checks that continuing background work stays working until terminal completion. Without `--live-bridge`, the fixtures start isolated bridge runtimes that can still discover USB hardware; unplug the Photon when testing without hardware. The [README contributing section](../README.md#contributing) lists hardware-free unit checks.
