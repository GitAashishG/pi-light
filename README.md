# pi-light

A USB desk indicator for OMP, using the RGB LED on an original Particle Photon.

## Current status

The host bridge and OMP integration are installed, and the original Photon is running pi-light over USB. Official Device OS2.3.1 system parts, bootloader1006 and the application were installed through Particle's supported local USB paths. Read-only device module inspection reported no validity/dependency errors. A real firmware handshake, all five state/RGB acknowledgments, actual OMP waiting/completion/error events, and board-facing webcam color stills passed.

Newly started default-profile OMP sessions pick up the installed loader. **Restart or explicitly reload older OMP sessions** to include them; setup does not interrupt or take over already-running sessions. macOS accessory approval was required once after firmware re-enumerated; the owner approved it, and no global security policy was changed. See [docs/OPERATIONS.md](docs/OPERATIONS.md) for recovery and physical-test details.

## What the light means

| State | Pattern |
|---|---|
| Working | Slow blue breath |
| Needs input | Amber pulse while an OMP question, tool approval, or plan review is pending |
| Complete | Three green flashes, then steady green until new work or session closure |
| Run error | Distinct red pulse for an unrecovered agent-run error |
| Idle | Very dim steady white |
| Host link lost | Slow dim-white breath after 15 seconds without a valid device heartbeat |

Across all live top-level OMP sessions, priority is **needs input, error, working, complete, idle**. A completed session does not hide another session that is still working. Root sessions include their continuing background work; subagents do not independently change the light. Ordinary failed tool calls that the agent is fixing do not mean the whole run failed. A user-aborted run becomes idle rather than green.

The board reports status only. It never answers a question, approves a tool, changes permissions, or sends a prompt. Questions asked only in free-form prose, macOS permission dialogs, terminal sudo/password prompts, and third-party applications are not guaranteed to emit the supported OMP events.

## Installation

From this directory, with `uv`, Bun, and Python available:

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/install.py
```

The guarded installer writes only:

- `~/.omp/agent/extensions/pi-light.ts`, a loader for `extension/index.ts` in this project.
- `~/.local/bin/pi-light`, the diagnostic command.
- A local installation receipt under `.local/`.

It refuses unrelated or modified installation targets and leaves existing Orca/Herdr extensions, models, approval settings, and other agent CLIs unchanged. The source must stay at this project path. Newly started default-profile OMP sessions discover the loader; existing sessions need an explicit extension reload or restart. The current controlling session is not forcibly restarted. No named profile directory was present when installed; a future named profile needs its own approved loader rather than an assumed shared configuration.

The first indicator event starts the private bridge automatically. It is not a login service and has no network listener. Session heartbeats refresh every three seconds; crashed publishers expire after twelve seconds. If the bridge itself crashes or loses USB, the firmware's independent fifteen-second watchdog changes to offline rather than keeping a stale success light.

## Diagnostics

```sh
pi-light status
pi-light query
pi-light stop
```

`status` is a cached host/device health read. `query` obtains a fresh device acknowledgment without renewing the firmware heartbeat and fails honestly if the device is unavailable. `stop` stops only this user's bridge; a live OMP session can start it again on a later heartbeat.

For a brief manual test, use an ordinary expiring session lease, then remove it:

```sh
pi-light notify waiting --session desk-test --seq 1
pi-light remove --session desk-test --seq 2
```

Manual tests do not override the priority of real sessions and expire after twelve seconds if not refreshed. `serve --brightness 24` can run a foreground bridge at lower brightness after stopping the existing owner. The default is 48, maximum 128. No external LED strip or additional sensor is required.

The private runtime directory is `~/.local/state/pi-light` (0700), with `bridge.sock` (0600). A directory lock prevents duplicate serial owners. Local clients use a strict bounded schema, sequence numbers and monotonic leases. Only opaque session identity, state and timing reach the bridge; only aggregate state, sequence and brightness reach the Photon. Prompts, code, paths, credentials and tool arguments are neither sent to the board nor logged by this project. The USB interface has no Wi-Fi or Particle cloud dependency.

## Build and tests

```sh
bash scripts/build-firmware.sh
.venv/bin/python -m unittest discover -s tests/host -p 'test_*.py' -v
bun test tests/extension.test.ts
make -C tests/firmware test
.venv/bin/python tests/runtime-smoke.py --installed
.venv/bin/python tests/async-runtime.py
```

The first build prepares project-local pinned Device OS 2.3.1 source, Arm GCC 9.2.1, and Particle's module parser. It runs recursive library dependencies before linking to avoid the SDK's clean parallel-build race. Output is `firmware/build/pi-light.bin`; the build never flashes. See [firmware/BUILD.md](firmware/BUILD.md) for hashes, platform/address validation and safe programming constraints.

`runtime-smoke.py` launches real OMP RPC processes and the actual extension with a deterministic local provider. Its question and intentional failure are test fixtures, not a paid model or a fabricated production status. It verifies waiting, two-session precedence, completion, run error and cleanup. Tool-approval scenarios only refuse their harmless test read; they never accept a safety approval. `--live-bridge` instead uses the normal private bridge and will briefly change the physical light after hardware setup is complete.

`async-runtime.py` exercises a real native background bash process through the actual installed loader. It observes the RPC nonterminal end, records the extension-converted event, holds the worker through a managed heartbeat interval, and requires working state until the worker is explicitly released and the session settles. Add `--live-bridge` to require matching physical Photon states; run that mode without other publishers so another session cannot mask an early-completion bug. The worker has a finite deadline, and cleanup releases only that owned fixture.

For the exclusive physical watchdog test, first stop the bridge, identify your own Photon locally, then run `.venv/bin/python tests/hardware-watchdog.py --device-id "$PHOTON_DEVICE_ID"`. The ID is required and must be 24 hexadecimal characters; there is no machine-specific default. This briefly controls the LED and exercises the real timeout. Restart the bridge afterward.

## Observed verification

- 39 Python bridge tests passed, including leases, ordering, precedence, socket ownership, malformed requests, USB handshake/ACK correlation, reconnect, query deadlines and cleanup. USB tests used an isolated fake peer, not the physical board.
- Six Bun state/publisher tests passed. Native firmware parser, watchdog, brightness, wrap and animation checks passed with address/undefined-behavior sanitizers; four module-header tests passed.
- Real OMP runtime tests passed through the actual installed loader and physical Photon: structured-question waiting, an explicitly denied test approval, two-session priority, terminal completion, unrecovered local-provider error and session-shutdown cleanup. The local provider emitted deterministic responses; no paid/external model was called. Each live aggregate assertion required a matching physical device acknowledgment.
- The modular application built as 5,580 bytes of text, 128 bytes of data and 1,896 bytes of BSS; the emitted binary passed Particle's platform-6, dependency, address-span and CRC checks. The two official system modules and application were flashed successfully using the supported CLI.
- The connected board initially had bootloader module2 and a monolithic layout. The separately approved official bootloader2.3.1 was installed through normal-mode Device OS, never a raw DFU bootloader write. Read-only hardware module inspection reported bootloader1006, both system parts2302, user module6, empty validity-error lists, and compatible dependencies.
- The board-facing webcam captured stills with no audio. An authorized temporary room-lighting check restored the light's original state. Household device names, entity IDs and credentials are not part of this source; room lighting is not part of the production agent indicator.

The real Photon reported working blue[0,0,5], waiting amber[8,2,0], done green[0,47,0], error red[47,0,0], and idle white[2,2,2] at sampled animation phases. Webcam stills independently showed the corresponding blue, orange/amber, green and red light; dark-room highlights bloom, so these are visual checks rather than calibrated color measurements. Evidence and isolated fixture logs are under ignored `.local/`. Native tests and bounded hardware checks are not an overnight soak.

The physical watchdog acceptance passed: after state heartbeats stopped, query/HELLO/invalid frames did not renew the timer and the board entered offline after15.366seconds. A repeated done heartbeat preserved the latched green output; the test ended in idle. The normal detached bridge was then restored through the same auto-start path used by the extension, and a fresh query reported the real connected Photon in idle with RGB[2,2,2] and zero test publishers. Detailed receipt: `.local/hardware-watchdog.json`.

The async-job yield regression also passed on the actual Photon. RPC emitted `isTerminal:false` with `awaitingAsyncWork:true`; the corresponding extension event carried `willContinue:true`. The installed production handler therefore kept working/blue across 57 status observations while the real worker remained pending, then reported done/green only after actual worker completion and `session_settled`. No production handler change was needed. Evidence: `.local/async-runtime/result.json`; reproduce with `.venv/bin/python tests/async-runtime.py --live-bridge`.

## Recovery and enclosure

Use the Photon’s RESET/SETUP buttons to enter DFU for recovery. Never select the unrelated ESP32 serial port, mass erase, overwrite DCT/key regions, or bypass a macOS permission prompt. The project does not claim or log in to a Particle account. A hardware bootloader upgrade was separately approved, with power-loss recovery risk disclosed.

The owner is printing the enclosure; see [docs/ENCLOSURE.md](docs/ENCLOSURE.md) for diffuser, USB strain relief, clearances and recovery-button access. The ESP32 thermometer logger remains a separate, untouched project.

To remove only this project's installed hooks/command:

```sh
pi-light stop
.venv/bin/python scripts/install.py --uninstall
```

The installer preserves modified files instead of deleting them. Firmware, project source and unrelated integrations remain in place.
