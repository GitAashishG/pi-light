# Original Photon firmware

Target: original Particle Photon / P0, Gen 2, STM32F205, Particle platform ID **6**. Photon 2/P2 (RTL872x), Boron and other boards are not compatible. The application rejects other platform IDs at compile time.

For device selection, flashing commands and recovery precautions, use [Build and flash the Photon](../docs/FIRMWARE.md). This reference covers the local build and firmware internals.

## Build and native tests

From the repository root:

```sh
bash scripts/build-firmware.sh
```

This prepares project-local prerequisites, then invokes Particle's modular `modules/photon/user-part` make target. It builds application firmware only, with the Device OS dynalib ABI and Particle module prefix, SHA suffix and CRC. It does not compile a monolithic STM32 image, flash anything, open serial devices, log in, claim a device or configure Wi-Fi.

Outputs:

- `firmware/build/pi-light.bin`: application module for the original Photon.
- `firmware/build/pi-light.elf`, `.map`, `.hex`, `.lst`: linked/debugging artifacts.
- `firmware/build/pi-light.module.json`: metadata and CRC checked by Particle's `binary-version-reader`.
- `firmware/build/pi-light.bin.sha256`: build output digest.

The build script runs `make_deps` before `all` to prevent a clean parallel build from linking before the Device OS dynalib archives exist. It then validates the application with `firmware/tools/inspect-module.cjs` and writes the module report and SHA-256 digest.

Use `JOBS=2 bash scripts/build-firmware.sh` to change parallelism. See the [README prerequisites](../README.md#prerequisites) for host tools. Particle's 2.x makefiles require a checkout path without spaces. The scripts do not install global tools or modify shell profiles. `BUN_BIN` may select an existing Bun executable.

Preparation without compiling:

```sh
bash scripts/prepare-firmware-tools.sh
```

Run the portable parser, watchdog and animation tests, plus saved-header decoder tests:

```sh
make -C tests/firmware test
```

The native target requires a C++14 compiler with AddressSanitizer and UndefinedBehaviorSanitizer, plus `python3` on `PATH`. It writes its executable under `firmware/build/native/` and needs neither the MCU SDK nor hardware. Coverage includes malformed input, the 96-byte line boundary, uint32 overflow, millis wrap, heartbeat timeout, completion latching, brightness zero and channel ceilings.

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
| Official module parser | npm `binary-version-reader@5.0.0` |
| Parser npm integrity | `sha512-VTom4XLIvGjZJJrqDBErjw1dxYZvQfCYv6SZjpb7tb0wYImxPKuqqC+XDQ+mO9nWw5VojkriETNKpCfN6wToCA==` |
| Parser peer package | `@particle/device-constants@4.2.1` |
| JS dependency lock | `firmware/tools/bun.lock`; frozen installation with package integrity hashes |

`v2.3.1` is marked prerelease in the upstream release metadata. It is the pinned original-Photon target, not a cloud compiler's default board or Device OS. The SHA-256 pins identify the public release artifacts; they are not independently signed vendor checksums.

The compiler is a macOS x86_64 executable. Intel Macs can run it directly; Apple Silicon requires working x86 translation support. Preparation checks `arm-none-eabi-gcc --version` but does not install Rosetta or change security/quarantine permissions. Docker, Particle CLI and `dfu-util` are not needed for compilation. Install Particle CLI separately for flashing, as described in the [flash guide](../docs/FIRMWARE.md#2-install-particle-cli-separately).

Preparation checks download digests before extraction, verifies the Device OS commit, initializes its pinned submodules, and installs locked metadata-reader packages with `--frozen-lockfile --ignore-scripts`. The compiler, source tree, downloads, system images and `node_modules` remain ignored local files. Inspect the source revision and submodules with:

```sh
git -C firmware/.tools/device-os-2.3.1 rev-parse HEAD
git -C firmware/.tools/device-os-2.3.1 submodule status --recursive
```

## Module layout and Device OS compatibility

The pinned Photon linker scripts and modular makefiles define this layout. These are module addresses, not raw flash-write instructions.

| Component | Address | Size limit | Required module metadata |
| --- | --- | --- | --- |
| pi-light user module | `0x080a0000` | 128 KiB including CRC | Platform 6, function 5, index 1; dependency system part 2 >=2302 |
| Photon system part 1, 2.3.1 | `0x08020000` | 256 KiB | Platform 6, function 4, index 1, version 2302; dependency system part 2 >=207 |
| Photon system part 2, 2.3.1 | `0x08060000` | 256 KiB | Platform 6, function 4, index 2, version 2302; dependencies system part 1 >=2302 and bootloader >=1003 |

Source references: [`modules/photon/modular.mk`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/photon/modular.mk), [`user-part/linker.ld`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/photon/user-part/linker.ld), [`user_build.mk`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/shared/stm32f2xx/user_build.mk), and [`system_module_version.mk`](https://github.com/particle-iot/device-os/blob/5aa7c8e1c7282b7c52040b77811186925d0febdc/modules/shared/system_module_version.mk).

The reference configuration is the pair of 2.3.1 system components with bootloader >=1003. A newer original-Photon Device OS can satisfy the encoded minimum dependency; check the complete module set for integrity and compatible dependencies before installing the application. Do not downgrade an already compatible device merely to match the build tag.

The official [2.3.1 release](https://github.com/particle-iot/device-os/releases/tag/v2.3.1) provides:

| File under `firmware/.tools/releases/` | SHA-256 |
| --- | --- |
| `photon-system-part1@2.3.1.bin` | `cf215e3564aa4e40ff12e73ba10a6092717984bacc87cfea3f5c6c15a19aadea` |
| `photon-system-part2@2.3.1.bin` | `b7d6965a357a5919e37bda6e031aef2f9a6dcfc583a8dbc928843a518cef6324` |

Direct public downloads (also pinned in preparation):

- [Photon system part 1](https://github.com/particle-iot/device-os/releases/download/v2.3.1/photon-system-part1%402.3.1.bin)
- [Photon system part 2](https://github.com/particle-iot/device-os/releases/download/v2.3.1/photon-system-part2%402.3.1.bin)

Preparation saves official-parser reports beside these binaries as `*.module.json`. To inspect them independently without touching hardware:

```sh
node firmware/tools/inspect-module.cjs 'firmware/.tools/releases/photon-system-part1@2.3.1.bin' system1
node firmware/tools/inspect-module.cjs 'firmware/.tools/releases/photon-system-part2@2.3.1.bin' system2
```

### Header-only inspection while already in DFU

For an original Photon already identified in DFU, read only the following 24-byte module prefixes. No application execution, network connection or configuration/key dump is needed. These are read locations, not write commands.

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

After saving precisely those bytes with explicitly targeted DFU reads, decode the local files with:

```sh
python3 firmware/tools/inspect-header.py --addresses
python3 firmware/tools/inspect-header.py bootloader firmware/build/headers/bootloader.bin
python3 firmware/tools/inspect-header.py system1 firmware/build/headers/system1.bin
python3 firmware/tools/inspect-header.py system2 firmware/build/headers/system2.bin
```

This helper opens local files only, reads at most 25 bytes, and rejects files that are not exactly 24 bytes or do not identify the expected Photon component/bounds. It reports installed version, dependencies and the pi-light minimum threshold. A header cannot establish CRC integrity, authenticity or executability; output explicitly says `not_checked_header_only`. Do not label its version check as a successful integrity check. An absent/old/monolithic header is a reason to stop and identify the installed layout, not to scan or dump unrelated flash regions.

### USB upgrades and recovery

Follow the [flash guide](../docs/FIRMWARE.md#3-identify-the-board-and-inspect-its-dependencies) to inspect installed modules and choose application-only, system-pair or bootloader recovery. `particle serial inspect` needs a running Device OS USB interface; it is not a DFU read command.

Bootloader updates must use Particle's supported normal/listening-mode Device OS updater, never a guessed raw DFU address. DFU application/system recovery cannot repair every bootloader failure. Keep power stable, preserve manufacturing data and keys, and stop if the installed layout or device identity is uncertain. During an incomplete system upgrade, safe mode may attempt network recovery before pi-light's Wi-Fi-off code runs.

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

