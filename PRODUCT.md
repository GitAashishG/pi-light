# pi-light

## Approved scope

The project uses an original Particle Photon as a USB desk indicator for top-level OMP sessions on a Mac. The enclosure is user-supplied; an external LED strip, Wi-Fi setup, Home Assistant integration, and changes to unrelated sensor projects are outside the scope.

## Behavior

- Working: restrained blue animation.
- Input needed: pulsing amber while an explicit OMP question, tool approval, or plan review awaits a response. Clear when it resolves. Never infer waiting from silence or parse conversation text.
- Complete: green transition flashes, then steady green until that session starts new work or closes.
- Error: red for an unrecovered agent-run error, not for individual failed tools that the agent is fixing.
- Idle: dim white when a healthy bridge has no active, waiting, failed, or completed sessions.
- Stale device link: a distinct slow dim-white pattern after the board stops receiving valid host heartbeats. Never leave a stale green/blue light indefinitely.
- Across live sessions, priority is waiting, error, working, complete, idle. A session shutdown or expired lease removes that session from aggregation. Subagents do not independently change the light; a main run with background work must not be reported complete early.

OMP public lifecycle documentation and existing local managed extensions confirm question/approval/plan-review and nonterminal-versus-terminal completion signals. Do not edit the existing Orca/Herdr managed extensions. A separate status-only extension uses public observability hooks and never blocks agent work when the indicator is unavailable.

## Privacy and safety

USB-only board control and a user-private Unix socket on the Mac; no TCP listener or cloud service. Only opaque session identity, state, sequence, and heartbeat timing reach the local bridge. Only aggregate state, sequence, and brightness reach the Photon. No prompt text, code, paths, credentials, tool arguments, or conversation contents are forwarded or logged. Never answer a question, approve a tool, invoke an approval action, change permissions, or infer consent.

Automatic integration is scoped to OMP on this Mac. Remote agents and other CLI adapters require separate approval; do not install incompatible hooks into other runtimes. The bridge/diagnostic CLI remains usable independently of OMP.

## Hardware and transport

The target is the original Photon (platform 6), with a built-in RGB LED and native USB serial after firmware boots. Use Device OS local compilation and USB flashing; no Particle account claim, cloud login, or Wi-Fi credentials. Preserve manufacturing/configuration/key regions, inspect firmware compatibility, and target only the explicitly identified Photon, never an unrelated serial device.

Bootloader and Device OS upgrades require explicit operator approval after power-loss/recovery risks are explained. Preserve manufacturing/configuration/key regions; do not mass erase, guess protected writes, claim an account, log in to the cloud, configure Wi-Fi, or alter unrelated hardware. Stop if target identity, official module integrity, compatibility, or the supported update route cannot be verified. Optional board-facing camera checks require consent and must not record audio or continuous video. Do not change persistent security or power settings for unattended work.

## Acceptance

Build and flash the actual Photon; handshake with its firmware and query real RGB/state acknowledgments. Prove working/waiting/completion and stale-link behavior on the connected board. Prove all-local-session aggregation, precedence, cleanup and nonterminal-run handling. Exercise actual OMP event emission through an isolated runtime test and, where possible, a real question/completion flow. No paid model calls or live safety-approval bypasses are needed for testing. Install the user extension without changing unrelated configuration, models, existing extensions, or other agents. Verify discovery and report which running sessions need reload/restart to pick up the extension; do not interrupt the current controlling session blindly.
