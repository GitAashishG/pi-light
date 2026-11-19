#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
FW="$ROOT/firmware"
TOOLS="$FW/.tools"
OS="$TOOLS/device-os-2.3.1"
OS_COMMIT=5aa7c8e1c7282b7c52040b77811186925d0febdc
COMPILER=gcc-arm-none-eabi-9-2019-q4-major
ARCHIVE="$TOOLS/$COMPILER-mac.tar.bz2"
COMPILER_SHA=1249f860d4155d9c3ba8f30c19e7a88c5047923cea17e0d08e633f12408f01f0
BUN=${BUN_BIN:-$(command -v bun || true)}

if [[ ${1:-} == --help ]]; then
    printf '%s\n' 'Usage: bash scripts/prepare-firmware-tools.sh' \
        'Downloads pinned official sources/compiler/Photon system modules into firmware/.tools.' \
        'Installs locked local metadata-reader dependencies with lifecycle scripts disabled.' \
        'Does not compile, flash, reset devices, access serial ports, or use Particle cloud.'
    exit 0
fi
[[ $# == 0 ]] || { echo 'Unexpected arguments' >&2; exit 1; }
[[ $(uname -s) == Darwin ]] || { echo 'This pinned compiler preparation supports macOS only.' >&2; exit 1; }
case "$ROOT" in *' '*) echo 'Particle 2.x makefiles require a project path without spaces.' >&2; exit 1;; esac
for tool in git curl tar shasum node make crc32 xxd; do
    command -v "$tool" >/dev/null || { echo "Missing required local tool: $tool" >&2; exit 1; }
done
[[ -n "$BUN" ]] || { echo 'Bun is required; set BUN_BIN to an existing installation.' >&2; exit 1; }
node -e 'const [a,b,c]=process.versions.node.split(".").map(Number); if(a<22 || (a===22 && (b<23 || (b===23 && c<4)))) { console.error("Node >=22.23.4 required by official module reader"); process.exit(1); }'
mkdir -p "$TOOLS/releases"

verify() {
    local file=$1 expected=$2 actual
    actual=$(shasum -a 256 "$file")
    actual=${actual%% *}
    [[ "$actual" == "$expected" ]] || { echo "SHA-256 mismatch: $file" >&2; exit 1; }
}
fetch() {
    local url=$1 file=$2 expected=$3
    if [[ ! -f "$file" ]]; then
        curl --fail --location --retry 2 --connect-timeout 20 --max-time 300 "$url" -o "$file.download"
        verify "$file.download" "$expected"
        mv "$file.download" "$file"
    fi
    verify "$file" "$expected"
}

fetch "https://developer.arm.com/-/media/Files/downloads/gnu-rm/9-2019q4/$COMPILER-mac.tar.bz2" \
    "$ARCHIVE" "$COMPILER_SHA"
if [[ ! -x "$TOOLS/$COMPILER/bin/arm-none-eabi-gcc" ]]; then
    tar -xjf "$ARCHIVE" -C "$TOOLS"
fi
# The official 2019 compiler is x86_64. This also checks existing Rosetta support
# on Apple Silicon; it never installs Rosetta or changes host security settings.
"$TOOLS/$COMPILER/bin/arm-none-eabi-gcc" --version

if [[ ! -d "$OS" ]]; then
    git clone --branch v2.3.1 --depth 1 https://github.com/particle-iot/device-os.git "$OS"
fi
[[ $(git -C "$OS" rev-parse HEAD) == "$OS_COMMIT" ]] || {
    echo "Existing Device OS source is not the pinned commit; leaving it untouched: $OS" >&2; exit 1;
}
git -C "$OS" submodule update --init --recursive --depth 1 --jobs 6

fetch 'https://github.com/particle-iot/device-os/releases/download/v2.3.1/photon-system-part1%402.3.1.bin' \
    "$TOOLS/releases/photon-system-part1@2.3.1.bin" \
    cf215e3564aa4e40ff12e73ba10a6092717984bacc87cfea3f5c6c15a19aadea
fetch 'https://github.com/particle-iot/device-os/releases/download/v2.3.1/photon-system-part2%402.3.1.bin' \
    "$TOOLS/releases/photon-system-part2@2.3.1.bin" \
    b7d6965a357a5919e37bda6e031aef2f9a6dcfc583a8dbc928843a518cef6324

(cd "$FW/tools" && "$BUN" install --frozen-lockfile --ignore-scripts)
node "$FW/tools/inspect-module.cjs" "$TOOLS/releases/photon-system-part1@2.3.1.bin" system1 \
    > "$TOOLS/releases/photon-system-part1@2.3.1.module.json"
node "$FW/tools/inspect-module.cjs" "$TOOLS/releases/photon-system-part2@2.3.1.bin" system2 \
    > "$TOOLS/releases/photon-system-part2@2.3.1.module.json"
printf '%s\n' 'Firmware sources, compiler and CRC-validated official system modules prepared locally.'
