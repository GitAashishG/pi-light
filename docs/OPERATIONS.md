# Operations and hardware handoff

## Hardware setup history

Hardware setup completed after the operator admitted the accessory. The test board was an original Photon, platform 6, DFU VID/PID `2b04:d006`, with bootloader module 2 and old monolithic firmware. Only 24-byte module headers were read; no DCT, keys or manufacturing region was dumped. Actual device identifiers remain in ignored local evidence, not this repository.

The owner explicitly approved a supported bootloader/Device OS upgrade for this board, including the power-loss recovery risk. The official Device OS2.3.1 system1/system2 binaries and locally built pi-light application passed platform/address/CRC validation, then Particle CLI3.52.5 reported successful local USB flashes for all three. After accessory admission, the official bootloader module1006 was installed through Particle's supported normal-mode local flash path. No mass erase, configuration-region write, cloud login, device claim or Wi-Fi setup occurred.

The board re-enumerated as a normal Particle Photon, VID/PID `2b04:c006`. macOS temporarily reported `device functionality blocked by transport restrictions` while locked. The operator unlocked/approved the accessory and its serial interface became accessible. No driver workaround or security-setting change was used. If a replug while locked hits this restriction again, unlock and approve the native accessory prompt instead of weakening policy.

Read-only `particle-usb.getFirmwareModuleInfo` reported bootloader1006, both system parts2302, user module6, no validity errors and satisfied dependencies. RESET/SETUP still provide DFU recovery. Do not write a bootloader directly to `0x08000000` over DFU; Particle's bootloader update path runs through Device OS in normal/listening mode.

## Upgrade/recovery reference (already completed)

Keep the board connected on the same USB cable, the Mac on power, and do not interrupt a bootloader update. Approve only the Photon accessory connection if macOS asks. Do not change global accessory policy or turn off the screen lock to work around it.

From the project root, inspect the admitted interface:

```sh
HOME="$PWD/.local/particle-home" node .tools/particle-cli/node_modules/particle-cli/src/index.js usb list
.venv/bin/python -m serial.tools.list_ports -v
```

Identify your original Photon's device ID from the local output and set `PHOTON_DEVICE_ID` explicitly before any update. If the device is missing, differs from your intended target, or multiple targets make identification ambiguous, stop and inspect before flashing. Never select an unrelated serial device. Device IDs and serial ports are machine-specific; no real identifier is included here.

The already-downloaded official bootloader is `firmware/.tools/releases/photon-bootloader@2.3.1+lto.bin`. Its locally checked properties are platform6, function2/index0, module1006, 15,124 bytes, valid CRC `d8161977`, SHA-256 `f6efd97c1b3e3c417a606a9b215c29a08cca49b07e524c2a3f8ea92b9d89b241`. The digest pins the downloaded public release, not an independently signed-vendor attestation. Validate before use:

```sh
node firmware/tools/inspect-module.cjs 'firmware/.tools/releases/photon-bootloader@2.3.1+lto.bin'
```

After exact identity and normal-mode access are confirmed, the approved remaining update is:

```sh
: "${PHOTON_DEVICE_ID:?Set this to the exact Photon ID verified above}"
HOME="$PWD/.local/particle-home" node .tools/particle-cli/node_modules/particle-cli/src/index.js flash --local "$PHOTON_DEVICE_ID" 'firmware/.tools/releases/photon-bootloader@2.3.1+lto.bin'
```

This supported CLI derives and validates module handling. It updates a bootloader through normal Device OS, not a guessed raw address. Do not use `--yes`, `--force`, bootloader DFU writes, factory reset, mass erase, or account login as a substitute for an error. Read back module integrity and dependencies after reboot using the installed CLI's documented serial inspection command, then require a real `PI-LIGHT 1 <device-id>` handshake before changing light states.

The automatic `particle update --target2.3.1` metadata endpoint rejected anonymous access with HTTP400/access-token-not-found. No token was acquired. Manual official binaries over the supported local CLI avoid that cloud-account dependency. Sources: [Particle versions/manual USB procedure](https://docs.particle.io/reference/device-os/versions/) and [official release](https://github.com/particle-iot/device-os/releases/tag/v2.3.1).

## Physical indicator acceptance

Once the bootloader, system and user dependencies pass and a serial interface is admitted:

1. Start `pi-light serve` or a newly loaded OMP session. `pi-light status` must show a real connected device with ID, ACK state and RGB; missing data must remain null.
2. Exercise an ordinary leased test publisher for working, waiting, done, error and idle, respecting normal aggregate priorities. Use `pi-light query` for fresh PWM-register-derived RGB acknowledgments. Repeat heartbeats must not restart green completion flashes.
3. Run `.venv/bin/python tests/runtime-smoke.py --installed --live-bridge` only when brief physical test patterns are appropriate. It uses a local deterministic provider, not a paid model. Its approval test selects Deny; no approval is accepted.
4. Observe the board with the authorized BRIO still-camera route. Hardware ACKs show applied register values, not optical brightness. Camera stills add optical evidence; do not infer correct colors from an unverified command acknowledgment alone.
5. Stop heartbeats for more than15seconds while querying only; the firmware must independently enter offline. A query/HELLO/malformed frame must not renew state. Restore the bridge and verify recovery.
6. Close publishers and verify shutdown or12-second lease expiration clears stale session states. The device must not remain green indefinitely after a crashed host.

Actual state/RGB feedback, live OMP waiting/completion/error/denied-approval events, multi-session priority and shutdown cleanup passed. Camera stills showed the expected blue, orange/amber, green and red light, with low-light bloom noted. Source-local receipts include `.local/physical-state-acks.json`, `.local/runtime-smoke/result.json`, `.local/installed-modules.json` and `.local/optical/`. Do not mistake the reproducible test checklist for a claim of a long-duration soak.

The final exclusive hardware test measured offline after15.366seconds while sending only queries, HELLO and invalid frames; none renewed the heartbeat. Repeated done state preserved the completion latch. The test restored idle, and the extension's normal detached bridge auto-start path successfully reconnected and queried idle RGB[2,2,2] with zero publishers at2026-11-19T04:53:35Z. `.local/hardware-watchdog.json` records the actual device result.

The async-job acceptance also passed with `.venv/bin/python tests/async-runtime.py --live-bridge`. A real native background bash process was held open through a managed heartbeat interval. RPC reported `isTerminal:false`/`awaitingAsyncWork:true`; the actual extension hook received `willContinue:true`. The host and physical Photon stayed working/blue across 57 status observations, then became done/green after the worker completed and `session_settled` arrived. The production handler was unchanged. Metadata-only conversion evidence and actual device ACKs are in `.local/async-runtime/result.json`; fixture logs contain only the deterministic local scenario, not user prompts or a paid-model call.

## Camera and office lighting

The user authorized board-facing webcam checks, with no audio or continuous recording. A single-frame route was verified with the Logitech BRIO:

```sh
ffmpeg -hide_banner -loglevel error -f avfoundation -pixel_format uyvy422 -framerate 30 -video_size 1280x720 -i '0:none' -vf 'select=gte(t\,1)' -frames:v 1 -an -update 1 -y .local/camera-check.png
```

Device indices can change after replug; enumerate camera devices first rather than selecting screen capture or the microphone. Keep stills private under ignored `.local/`.

Optional room lighting is outside the indicator runtime. Control it only with explicit permission for the exact device, record its initial state, independently verify each change, and restore the initial state in `finally`. Keep home-automation credentials in an external secret workflow; never copy them, household device names or entity IDs into this repository. The indicator works without Home Assistant or lamp-control credentials.

## Session/daemon lifecycle

The user-level extension is loaded by newly started default-profile OMP sessions. It ignores `ctx.agent.kind === sub` and publishes only state/opaque identity. No hook modifies tool input/results or answers an approval. Existing Orca/Herdr managed extensions remain untouched. Existing sessions are not forcibly reloaded.

The daemon autostarts on a publisher connection failure and has a single-owner lock, private Unix socket, bounded client/serial I/O, publisher sequence ordering and leases. It is not a login service. `pi-light stop` stops it; another live OMP heartbeat can start it again. Current device state and desired aggregate are distinct. A disconnected device is never reported connected because a session update succeeded.

The task-scoped caffeinate guard only prevents idle system sleep while setup runs. It does not unlock the Mac, keep a display awake, approve accessories or change persistent power/security settings. Stop the guard when unattended setup is finished or blocked awaiting the owner. It is not part of pi-light's installed runtime.
