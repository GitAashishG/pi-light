# Build and flash the Photon

This guide targets the **original Particle Photon**, Gen 2, STM32F205, platform 6. Do not use these binaries on Photon 2/P2, Boron, Spark Core, or ESP32. Flashing replaces the board's current application.

Run project commands from the repository root. Start with the [README prerequisites](../README.md#prerequisites). The build uses official Device OS **2.3.1** and Arm GCC **9.2.1**. The upstream 2.3.1 release is marked prerelease; it is this project's pinned original-Photon target, not a request to install the latest Device OS for another board.

## 1. Build the application

```sh
bash scripts/build-firmware.sh
```

The script prepares its own ignored files under `firmware/.tools/`, checks download hashes and the Device OS commit, and builds only the Photon user module. It validates the binary's CRC, platform, address span, and dependency metadata. It never opens a device or flashes firmware.

The outputs needed here are:

- `firmware/build/pi-light.bin`, the application.
- `firmware/build/pi-light.module.json`, its validation report.
- `firmware/.tools/releases/photon-system-part1@2.3.1.bin` and `photon-system-part2@2.3.1.bin`, the official system modules downloaded during preparation.

There are no prebuilt application binaries in a fresh clone. To download tools and system modules without compiling, use `bash scripts/prepare-firmware-tools.sh`. `JOBS=2 bash scripts/build-firmware.sh` changes build parallelism; `BUN_BIN` can select an existing Bun executable.

The pinned compiler is a macOS x86_64 executable. On Apple Silicon, translation support must already work. The scripts do not install Rosetta, remove quarantine attributes, or change host security policy. A checkout path with spaces is not supported by these Device OS makefiles.

## 2. Install Particle CLI separately

The build script does **not** install Particle CLI. Use Particle's [official CLI installation instructions](https://docs.particle.io/getting-started/developer-tools/cli/). The commands below follow CLI **3.52.5**; read your installed command's help before writing firmware.

For a fresh macOS installation, you can download and review the upstream installer before running it:

```sh
cli_installer="$(mktemp)"
curl --fail --location https://particle.io/install-cli -o "$cli_installer"
less "$cli_installer"
VERSION=3.52.5 bash "$cli_installer"
rm "$cli_installer"
```

The upstream installer installs `~/bin/particle`, may add `~/bin` to existing shell profiles, and may install a missing OpenSSL dependency through Homebrew. Review those changes first. If you already have a working CLI, do not replace it just for this project; select its actual executable below and compare its help.

```sh
PARTICLE="$HOME/bin/particle"
"$PARTICLE" --version
"$PARTICLE" flash --help
"$PARTICLE" serial inspect --help
"$PARTICLE" usb list --help
```

These USB procedures do not require `particle login`, a claimed device, Wi-Fi setup, or cloud compilation. Do not run `particle flash` with an omitted binary or a source directory: its default compiler can be the cloud compiler. This project builds its own binary in step 1.

## 3. Identify the board and inspect its dependencies

Close OMP sessions using pi-light and any manual publishers before working on USB. If the bridge is installed, stop it with `~/.local/bin/pi-light stop` and allow it to exit. Close serial monitors. Disconnect other Particle boards to reduce selection mistakes, but still use an explicit device ID for each write.

Connect the original Photon with a data-capable USB cable:

```sh
"$PARTICLE" usb list
"$PARTICLE" serial list
```

Confirm the board is an original Photon, platform 6. Copy its own device ID and serial port from local output, not from someone else's instructions:

```sh
printf 'Original Photon device ID: '
read -r PHOTON_DEVICE_ID
printf 'Original Photon serial port: '
read -r PHOTON_PORT
"$PARTICLE" serial inspect --port "$PHOTON_PORT"
```

Keep these values and inspection output private. The ID should be 24 hexadecimal characters. Verify it again after USB mode changes; the serial port can change when firmware re-enumerates.

[`particle serial inspect`](https://docs.particle.io/troubleshooting/guides/device-troubleshooting/using-particle-serial-inspect/) reads the running Device OS USB interface. It is not a DFU read command. Use normal or listening mode for inspection. If macOS asks to allow the accessory, handle that prompt yourself; do not disable accessory protection or grant global permissions.

The application needs system part 2 module version **2302 or newer**. For the official 2.3.1 pair used here, the required set is:

| Component | Required version |
| --- | --- |
| System part 1 | 2302 |
| System part 2 | 2302 |
| Bootloader | At least 1003 |

Both system parts must be mutually compatible. Check integrity, platform, address-range, and dependency results, not just version numbers. A newer original-Photon system may satisfy the minimum; do not downgrade a compatible board merely to match the build tag. The pinned 2.3.1 set is the reference configuration for this project.

If inspection cannot identify the installed layout, stop before writes. The [low-level reference](../firmware/BUILD.md#header-only-inspection-while-already-in-dfu) describes limited saved-header inspection for old firmware. A decoded header alone does not establish module integrity. Do not guess addresses, dump unrelated flash, or treat an unknown/monolithic image as a compatible modular installation.

## 4. Choose the appropriate flash path

Review the complete path before starting. Keep power stable and do not unplug during programming. System upgrades change more than the application. **A bootloader update interrupted by power loss can leave the board needing hardware recovery.** Skip it if the installed bootloader already satisfies the required system dependencies.

### Compatible system and bootloader: application only

If inspection shows a compatible system/bootloader set with passing checks:

```sh
"$PARTICLE" flash --local "$PHOTON_DEVICE_ID" firmware/build/pi-light.bin --application-only
```

`--application-only` prevents automatic Device OS replacement. The CLI may look up version metadata, but the precompiled application does not need a cloud build or account. A metadata lookup failure is not a reason to log in or change the device target.

### Older system: install the pinned system pair

If the bootloader is at least 1003 but the system is too old, install the two prepared official system modules and the application together:

```sh
"$PARTICLE" flash --local "$PHOTON_DEVICE_ID" \
  'firmware/.tools/releases/photon-system-part1@2.3.1.bin' \
  'firmware/.tools/releases/photon-system-part2@2.3.1.bin' \
  firmware/build/pi-light.bin
```

Particle CLI validates module metadata and chooses the module destinations. Pass these binary files explicitly, not the source tree, a mixed-platform release directory, or arbitrary flash addresses. The CLI switches USB modes as needed. For a device already in DFU, confirm its ID with `usb list` again before flashing.

To enter DFU manually, hold SETUP, tap RESET, and keep holding SETUP until the LED blinks yellow. See Particle's [device mode guide](https://docs.particle.io/troubleshooting/led/). DFU is for application/system recovery here, **not a raw bootloader write**.

### Bootloader below 1003: supported Device OS update

Download the official original-Photon bootloader only if the installed version needs upgrading:

```sh
BOOTLOADER='firmware/.tools/releases/photon-bootloader@2.3.1+lto.bin'
curl --fail --location \
  'https://github.com/particle-iot/device-os/releases/download/v2.3.1/photon-bootloader%402.3.1%2Blto.bin' \
  -o "$BOOTLOADER"
printf '%s  %s\n' \
  f6efd97c1b3e3c417a606a9b215c29a08cca49b07e524c2a3f8ea92b9d89b241 \
  "$BOOTLOADER" | shasum -a 256 -c -
node firmware/tools/inspect-module.cjs "$BOOTLOADER"
```

Do not flash if either check fails. The file should identify platform 6, bootloader function 2/index 0, version 1006. The hash pins the downloaded release artifact; it is not an independently signed vendor checksum.

The bootloader must be installed through Particle's supported **normal/listening-mode Device OS updater**, never by a raw DFU write. With a working Device OS USB interface, recheck `usb list` and the exact device ID, then run:

```sh
"$PARTICLE" flash --local "$PHOTON_DEVICE_ID" "$BOOTLOADER"
```

Let the updater finish, inspect again, and require bootloader version at least 1003 before installing the pinned system pair above. Do not add `--yes`, bypass a permission prompt, or substitute `dfu-util` at a bootloader address.

#### Very old or monolithic firmware

Some old installations cannot run the supported USB bootloader updater until a modular Device OS is present. After positively identifying that layout and the original Photon, the recovery order is:

1. Enter DFU and use the explicit three-file system-pair/application command above to stage the official modular system and application.
2. Let the board restart, then enter listening mode by holding SETUP until it blinks blue. Re-enumerate with `usb list` and `serial list`; confirm the same device identity and update the port value if necessary.
3. Run the normal/listening-mode bootloader command above. Inspect the complete module set again before starting pi-light.

Until the bootloader dependency is satisfied, the application may not run. Device OS safe mode can attempt network recovery using existing configuration, so the application's Wi-Fi-off behavior does not apply during this intermediate state. If that is unacceptable, do not start this old-board recovery path. If the board cannot expose a supported Device OS USB interface after staging, stop and use Particle's [manual programming guidance](https://docs.particle.io/reference/developer-tools/programming-devices/); do not force a bootloader DFU write.

The automatic `particle update --target 2.3.1` route can require account-backed version metadata. The explicit public-module procedure above avoids making that updater or a Particle account an installation prerequisite.

## 5. Check the result

After USB re-enumerates, select the current Photon port and inspect again:

```sh
"$PARTICLE" usb list
"$PARTICLE" serial list
printf 'Current original Photon serial port: '
read -r PHOTON_PORT
"$PARTICLE" serial inspect --port "$PHOTON_PORT"
```

Require the expected platform, compatible module dependencies, and passing integrity/address checks. Flash-command success alone does not show that the application runs.

Return to the [host installation steps](../README.md#3-install-the-host-integration), start a newly loaded OMP session, and run `~/.local/bin/pi-light query`. A successful fresh acknowledgment with `device.connected: true` confirms the bridge is talking to pi-light. The README's manual notification test lets you check the visible LED patterns.

For recovery, preserve manufacturing data, keys, and configuration. Do not mass erase, factory reset, write DCT/key regions, claim the device, or configure Wi-Fi merely to install this application. See [firmware/BUILD.md](../firmware/BUILD.md) for pinned sources, module bounds, and firmware internals.
