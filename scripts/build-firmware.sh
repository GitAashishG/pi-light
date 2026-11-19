#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
FW="$ROOT/firmware"
if [[ ${1:-} == --help ]]; then
    printf '%s\n' 'Usage: bash scripts/build-firmware.sh' \
        'Prepares pinned local prerequisites, then compiles only the original Photon user module.' \
        'Outputs firmware/build/pi-light.{bin,elf,map,hex,lst} and pi-light.module.json.' \
        'Never flashes or resets hardware. Optional JOBS controls make parallelism (default 4).'
    exit 0
fi
[[ $# == 0 ]] || { echo 'Unexpected arguments' >&2; exit 1; }
JOBS=${JOBS:-4}
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo 'JOBS must be a positive integer.' >&2; exit 1; }

bash "$ROOT/scripts/prepare-firmware-tools.sh"
mkdir -p "$FW/build"
# This official modular target links against the pinned Device OS dynalib ABI and
# generates the Particle prefix, SHA suffix and CRC. Do not replace with a raw
# STM32 linker script or use a bootloader/system/monolithic build target.
BUILD=(make -C "$FW/.tools/device-os-2.3.1/modules/photon/user-part" -j"$JOBS"
    PLATFORM=photon
    APPDIR="$FW/src"
    TARGET_DIR="$FW/build"
    TARGET_FILE=pi-light
    GCC_ARM_PATH="$FW/.tools/gcc-arm-none-eabi-9-2019-q4-major/bin/")
# Device OS 2.x lists recursive libraries and ELF as sibling prerequisites;
# on a clean parallel build the ELF can otherwise race missing archives.
"${BUILD[@]}" make_deps
"${BUILD[@]}" all
node "$FW/tools/inspect-module.cjs" "$FW/build/pi-light.bin" user > "$FW/build/pi-light.module.json"
shasum -a 256 "$FW/build/pi-light.bin" > "$FW/build/pi-light.bin.sha256"
printf '\n%s\n' "Built and metadata-checked: $FW/build/pi-light.bin" \
    "Module metadata: $FW/build/pi-light.module.json" \
    'Nothing has been flashed. Inspect installed Photon system modules before flashing.'
