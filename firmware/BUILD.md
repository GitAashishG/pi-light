# Original Photon firmware

Target: original Particle Photon / P0, Gen 2, STM32F205, Particle platform ID **6**. Photon 2/P2 (RTL872x), Boron and other boards are not compatible. The application rejects other platform IDs at compile time.

## Build and native tests

From the project root on this Mac:

```sh
bash scripts/build-firmware.sh
```

This prepares project-local prerequisites, then invokes Particle's modular `modules/photon/user-part` make target. It builds application firmware only, with the Device OS dynalib ABI and Particle module prefix, SHA suffix and CRC. It does not compile a monolithic STM32 image, flash anything, open serial devices, log in, claim a device or configure Wi-Fi.

Outputs:

- `firmware/build/pi-light.bin`: application module for the original Photon.
- `firmware/build/pi-light.elf`, `.map`, `.hex`, `.lst`: linked/debugging artifacts.
- `firmware/build/pi-light.module.json`: metadata and CRC checked by Particle's `binary-version-reader`.
- `firmware/build/pi-light.bin.sha256`: build output digest.

The equivalent compilation command, after preparation, is:

```sh
make -C firmware/.tools/device-os-2.3.1/modules/photon/user-part -j4 \
  PLATFORM=photon \
  APPDIR="$PWD/firmware/src" \
  TARGET_DIR="$PWD/firmware/build" \
  TARGET_FILE=pi-light \
  GCC_ARM_PATH="$PWD/firmware/.tools/gcc-arm-none-eabi-9-2019-q4-major/bin/" all
node firmware/tools/inspect-module.cjs firmware/build/pi-light.bin user
```

Use `JOBS=2 bash scripts/build-firmware.sh` to change parallelism. Particle's 2.x makefiles require a project path without spaces. Native prerequisites are `git`, `curl`, `tar`, `shasum`, GNU `make`, `crc32`, `xxd`, Node >=22.23.4, and Bun with text-lockfile support. The scripts do not install global tools or modify shell profiles. `BUN_BIN` may select an existing Bun executable.

Preparation without compiling:

```sh
bash scripts/prepare-firmware-tools.sh
```

Portable parser/watchdog/animation tests, including malformed and 96-byte boundaries, uint32 overflow, millis wrap, heartbeat timeout, completion latching, brightness zero and channel ceilings:

```sh
make -C tests/firmware test
```

The native target uses C++14, AddressSanitizer and UndefinedBehaviorSanitizer and writes only under `firmware/build/native/`. It does not require the MCU SDK or hardware. Neither this test target nor the firmware build was executed during the firmware implementation handoff; the integration owner runs them.

## Pinned sources and tools

[Particle's local gcc-arm instructions](https://docs.particle.io/archives/local-build-using-gcc-arm/) require GCC 9.2.1 / `9-2019-q4-major` for Device OS 2.x. The pinned source's [Workbench manifest](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/.workbench/manifest.json) names `gcc-arm@9.2.1`. The make target follows the official [external APPDIR build instructions](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/docs/build.md).

| Item | Pin / provenance |
| --- | --- |
| Device OS | Official `https://github.com/particle-iot/device-os.git`, tag `v2.3.1`, commit `5aa7c8e1c7282b7c52040b77811186925d0febdc` |
| Source destination | `firmware/.tools/device-os-2.3.1`; recursive submodules use the exact gitlinks in that commit, never branch tips |
| ARM compiler | Official Arm GNU Tools for Arm Embedded Processors, `9-2019-q4-major`, GCC `9.2.1 20191025`, ARM branch revision `277599` |
| Compiler download | `https://developer.arm.com/-/media/Files/downloads/gnu-rm/9-2019q4/gcc-arm-none-eabi-9-2019-q4-major-mac.tar.bz2` |
| Compiler destination | `firmware/.tools/gcc-arm-none-eabi-9-2019-q4-major/` |
| Compiler archive SHA-256 | `1249f860d4155d9c3ba8f30c19e7a88c5047923cea17e0d08e633f12408f01f0` |
| Compiler upstream Content-MD5 | `241b64f0578db2cf146034fc5bcee3d4`, matching the downloaded archive |
| Official module parser | npm `binary-version-reader@5.0.0`, Particle-maintained source commit `80e8f7063d03f6c97f55d41b2655c9af26b7f03a`, Apache-2.0 |
| Parser npm integrity | `sha512-VTom4XLIvGjZJJrqDBErjw1dxYZvQfCYv6SZjpb7tb0wYImxPKuqqC+XDQ+mO9nWw5VojkriETNKpCfN6wToCA==` |
| Parser peer package | `@particle/device-constants@4.2.1` |
| JS dependency lock | `firmware/tools/bun.lock`; SHA-256 `65c22e977478f3bc595bc83b2561ed62f1b2160710e6d6e9a9bba87bb34d9b52` |

`v2.3.1` is marked prerelease in the upstream release metadata. This is an explicit 2.x target that includes Photon binaries, not a cloud compiler's current/default-board assumption. Source and public artifacts came from the URLs above over HTTPS. The SHA-256 pins were computed from those downloaded artifacts, not claimed as independently signed vendor checksums.

The compiler is a macOS x86_64 executable. On this arm64 Mac its `--version` command executed successfully using the already-available translation support. Preparation checks that executable but does not install Rosetta or change security/quarantine permissions. GNU Make 3.81, Node v26.11.1, Bun 1.4.2, `/usr/bin/crc32` and `/usr/bin/xxd` were available. Docker's selected OrbStack socket was absent; the native build does not use Docker. Particle CLI and dfu-util are not prerequisites for compilation and were not installed by this component.

The preparation script checks download digests before extraction, verifies the Device OS commit, initializes its pinned submodules, and installs locked metadata-reader packages with `--ignore-scripts`. The compiler, source tree, downloads, system images and node_modules remain ignored local files. To inspect the exact upstream source snapshot later:

```sh
git -C firmware/.tools/device-os-2.3.1 rev-parse HEAD
git -C firmware/.tools/device-os-2.3.1 submodule status --recursive
```

## Module layout and Device OS compatibility

The official Photon linker scripts, modular makefiles and inspected release binaries agree on this layout. These are module addresses, not authorization to write arbitrary flash.

| Component | Address | Size limit | Required module metadata |
| --- | --- | --- | --- |
| pi-light user module | `0x080a0000` | 128 KiB including CRC | Platform 6, function 5, index 1; dependency system part 2 >=2302 |
| Photon system part 1, 2.3.1 | `0x08020000` | 256 KiB | Platform 6, function 4, index 1, version 2302; dependency system part 2 >=207 |
| Photon system part 2, 2.3.1 | `0x08060000` | 256 KiB | Platform 6, function 4, index 2, version 2302; dependencies system part 1 >=2302 and bootloader >=1003 |

Source references: [`modules/photon/modular.mk`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/photon/modular.mk), [`user-part/linker.ld`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/photon/user-part/linker.ld), [`user_build.mk`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/shared/stm32f2xx/user_build.mk), and [`system_module_version.mk`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/shared/system_module_version.mk).

The exact validated system target is the pair of 2.3.1 components with bootloader >=1003. A newer original-Photon Device OS can satisfy the encoded minimum dependency, but has not been validated by this handoff. Do not downgrade an already compatible device just to match the build tag. The current connected device's installed modules were not inspected by this worker.

The official [2.3.1 release](https://github.com/particle-iot/device-os/releases/tag/v2.3.1) provides:

| Downloaded file under `firmware/.tools/releases/` | SHA-256 | Observed CRC |
| --- | --- | --- |
| `photon-system-part1@2.3.1.bin` | `cf215e3564aa4e40ff12e73ba10a6092717984bacc87cfea3f5c6c15a19aadea` | `13055d01`, valid |
| `photon-system-part2@2.3.1.bin` | `b7d6965a357a5919e37bda6e031aef2f9a6dcfc583a8dbc928843a518cef6324` | `bded86f5`, valid |

Direct public downloads (also pinned in preparation):

- [Photon system part 1](https://github.com/particle-iot/device-os/releases/download/v2.3.1/photon-system-part1%402.3.1.bin)
- [Photon system part 2](https://github.com/particle-iot/device-os/releases/download/v2.3.1/photon-system-part2%402.3.1.bin)

Preparation saves official-parser reports beside these binaries as `*.module.json`. To inspect them independently without touching hardware:

```sh
node firmware/tools/inspect-module.cjs 'firmware/.tools/releases/photon-system-part1@2.3.1.bin' system1
node firmware/tools/inspect-module.cjs 'firmware/.tools/releases/photon-system-part2@2.3.1.bin' system2
```

### Header-only inspection while already in DFU

The integration owner can read just the following 24-byte module prefixes. No application execution, network connection or configuration/key dump is needed. These are read locations, not write commands.

| Component | Module start | Prefix offset | Read address | Read length |
| --- | --- | --- | --- | --- |
| Bootloader | `0x08000000` | `0x184` | `0x08000184` | 24 bytes |
| System part 1 | `0x08020000` | `0x184` | `0x08020184` | 24 bytes |
| System part 2 | `0x08060000` | `0x184` | `0x08060184` | 24 bytes |
| Modular user part | `0x080a0000` | `0` | `0x080a0000` | 24 bytes |

Authoritative pinned sources:

- [`hal/src/photon/ota_module_bounds.c:4-9`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/hal/src/photon/ota_module_bounds.c#L4-L9) defines the module bases and flash bounds.
- [`build/arm/linker/linker_stm32f2xx_bootloader.ld:24-30`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/build/arm/linker/linker_stm32f2xx_bootloader.ld#L24-L30) and [`linker_stm32f2xx_common.ld:193`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/build/arm/linker/linker_stm32f2xx_common.ld#L193) place/assert the bootloader prefix at base+`0x184`.
- [`part1_vtor_module.ld:8-18`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/shared/stm32f2xx/part1_vtor_module.ld#L8-L18) and [`module_system_part2_export.ld:4-18`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/photon/system-part2/module_system_part2_export.ld#L4-L18) define the two system prefixes.
- [`user.ld:7-12`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/shared/stm32f2xx/user.ld#L7-L12) places the modular user prefix before its dynalib table, directly at the module base.
- [`module_info.h:53-79`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/dynalib/inc/module_info.h#L53-L79) defines/asserts the exact 24-byte packed layout.

Each header is little endian: start/end pointers at offsets 0/4, reserved/flags at 8/9, uint16 module version at 10, uint16 platform ID at 12, function/index at 14/15, and two four-byte dependencies at 16/20 (uint8 function, uint8 index, uint16 minimum version). The system/bootloader prefix offset is also the runtime rule in `FLASH_ModuleInfo` at `platform/MCU/STM32F2xx/SPARK_Firmware_Driver/src/flash_mal.c:675-696` when the module begins with a Cortex stack pointer.

After the integration owner saves precisely those bytes using explicitly targeted DFU reads, decode the local files with:

```sh
python3 firmware/tools/inspect-header.py --addresses
python3 firmware/tools/inspect-header.py bootloader firmware/build/headers/bootloader.bin
python3 firmware/tools/inspect-header.py system1 firmware/build/headers/system1.bin
python3 firmware/tools/inspect-header.py system2 firmware/build/headers/system2.bin
```

This helper opens local files only, reads at most 25 bytes, and rejects files that are not exactly 24 bytes or do not identify the expected Photon component/bounds. It reports installed version, dependencies and the pi-light minimum threshold. A header cannot establish CRC integrity, authenticity or executability; output explicitly says `not_checked_header_only`. Do not label its version check as a successful integrity check. An absent/old/monolithic header is a reason to stop and identify the installed layout, not to scan or dump unrelated flash regions.

### Integration owner's USB upgrade procedure

No flashing/reset/serial commands were run during this component's implementation. Before any write, identify the exact original Photon and capture its installed module inventory. The [official inspection guide](https://docs.particle.io/troubleshooting/guides/device-troubleshooting/using-particle-serial-inspect/) documents `particle serial inspect`; it requires a running Device OS USB interface and is not a DFU read command. Use the CLI's explicit device/port selector after reading that installed version's help. Never select `/dev/cu.usbserial-110`, which belongs to the unrelated ESP32.

If the installed system dependencies already satisfy the table, install only the CRC-checked user module. If they do not, use only the platform-6 official components above and Particle's [USB manual module programming procedure](https://docs.particle.io/reference/developer-tools/programming-devices/). The supported CLI accepts precompiled modules with `particle flash --local <device-id> <binary-or-module-directory>` and derives destinations from module metadata. When staging multiple files, use a dedicated directory containing only the required original-Photon components and the built pi-light application, never the source tree or a mixed-platform release directory. Read the local CLI's help first; do not invoke source compilation or leave its Device OS target at a modern-board default.

If the installed bootloader is below module version 1003, the two system parts alone have an unmet dependency. Use Particle's supported USB updater with an explicit original-Photon Device OS target, `particle update --target 2.3.1`, after confirming its exact device selector from that CLI's help. This requires a separate integration decision: it can update the bootloader as well as system firmware. Do not manually write a bootloader at a guessed address or bypass module validation. The release's `photon-bootloader@2.3.1+lto.bin` exists publicly, but this preparation intentionally does not download, flash or replace it.

Do not use `particle login`, claim/setup commands, Wi-Fi setup, a cloud compile, factory reset, mass erase, DCT/key writes, or bootloader replacement merely to install the application. Do not boot a mismatched user/system set and assume `SYSTEM_MODE(MANUAL)` already applies: unmet dependencies can enter safe mode before application code runs, and safe mode can attempt network recovery. Preserve the device's bootloader, manufacturing data, keys and credentials. Inspect the resulting module integrity/dependencies and USB handshake after an authorized flash; build metadata alone is not evidence that the hardware runs.

## Runtime implementation

`src/light_core.*` has no Particle SDK dependency. It parses strict LF-only physical lines with a 96-byte fixed buffer, discards rejected input through LF, detects uint32 overflow and validates state/brightness before applying a heartbeat. `HELLO`, queries and invalid frames do not renew it. Unsigned subtraction enforces the 15000 ms timeout across millis wrap.

The Photon adapter processes at most 64 input bytes and two 64-byte transmit batches per loop, with a fixed 384-byte reply queue. USB overrun blocking is disabled. A peer that stops reading cannot stall the state machine. There are no delays or dynamic allocations in parser, animation or serial response paths.

`SYSTEM_MODE(MANUAL)` and startup `WiFi.off()` prevent application Wi-Fi/cloud startup. `RGB.control(true)` owns the built-in LED. Brightness 0..128, default 48, is applied by the core; Device OS global RGB brightness stays 255. Acknowledgments use Device OS `LED_RGB_Get`, which reads the actual PWM compare registers and converts them to channels 0..255. This reflects brightness/quantization and is not a claim of optical measurement.

Animations use integer smoothstep envelopes and millis timing:

| State | Pattern |
| --- | --- |
| working | Blue breath, 3000 ms period |
| waiting | Amber breath, 1200 ms period |
| done | Three green 500 ms on/500 ms off flashes, then steady green |
| error | Red 500 ms on/500 ms off/500 ms on/1500 ms off, repeating |
| idle | Steady white at brightness/16, minimum 1 when nonzero |
| offline | White breath, 5000 ms period, peak brightness/6, minimum peak 1 when nonzero |

No configured pattern strobes above 1 Hz. Repeated state heartbeats and brightness changes preserve the animation epoch. Completion latches after its three flashes, including across long uptime; leaving/re-entering done starts a new transition. Brightness 0 keeps all channels off, including offline. The board starts offline until the first valid state command.

## Integration results on the actual board

The build and native tests have now run successfully. A clean parallel SDK build initially raced a missing dynalib archive; `scripts/build-firmware.sh` now runs `make_deps` before `all` without modifying upstream sources. The resulting application has5,580bytes text,128bytes data and1,896bytes BSS, valid CRC and the documented platform6/system2302 dependency.

Read-only initial headers identified bootloader2 and a monolithic platform6 application. The owner separately approved the necessary bootloader/Device OS upgrade. Particle CLI3.52.5 local `flash --usb` successfully wrote the two official2.3.1 system parts and pi-light user module. macOS then blocked the new normal-mode USB interface while locked; the owner admitted the accessory, rather than weakening a security policy. The official bootloader was installed through `flash --local` in normal/listening mode. No raw bootloader DFU write, mass erase, DCT/key dump, cloud login, device claim or Wi-Fi setup occurred.

Official bootloader artifact: `photon-bootloader@2.3.1+lto.bin`, module1006,15,124bytes, CRC`d8161977`, SHA-256`f6efd97c1b3e3c417a606a9b215c29a08cca49b07e524c2a3f8ea92b9d89b241`. The source is the same public official2.3.1 GitHub release. The automatic updater's version-metadata API required a cloud token, so the supported manual local-module procedure was used instead.

Particle USB's read-only `getFirmwareModuleInfo` on the test Photon reported bootloader 1006, system1/system2 version 2302 and user module 6, with empty validity-error lists and compatible dependencies. The physical firmware handshake and all expected state/RGB acknowledgments passed. These are actual hardware results, distinct from file-only parser checks. Device identifiers and raw receipts remain in ignored local evidence. See `docs/OPERATIONS.md` for the event/USB/camera acceptance procedure.

