# Changelog

## 0.1.0 — 2026-11-19

- Implemented original Photon USB-only RGB state firmware, bounded parser/queues, nonblocking animations and independent stale-heartbeat watchdog.
- Added a user-private Unix bridge with Photon-only handshake, correlated serial ACKs, monotonic session leases, multi-session priorities and reconnect handling.
- Added a separate status-only OMP extension for structured questions, approvals, plan reviews, run activity, terminal completion/error and cleanup, without editing existing managed extensions.
- Added guarded user installation and a portable diagnostic command; no non-OMP hooks, LAN API, credentials, Wi-Fi setup or Particle account claim.
- Built and validated the Photon application, flashed the official system modules/application, and completed the separately approved bootloader update through Particle's supported normal-mode USB path. After owner accessory approval, real module integrity/dependencies, firmware handshake, RGB acknowledgments, webcam colors and live OMP-to-device events passed; no security policy was weakened.
- Added native firmware and host/extension tests plus model-free tests through actual OMP RPC event emission.
- Added a real owned async-bash yield regression through the installed OMP loader and physical Photon. Verified RPC nonterminal ends convert to extension `willContinue:true`, preserve blue while the job is pending, and turn green only after actual worker completion and session settlement; no production-handler or firmware change was needed.
- Verified board-facing webcam still access without audio or continuous recording; optional temporary room lighting was restored. The production indicator has no home-automation dependency.
