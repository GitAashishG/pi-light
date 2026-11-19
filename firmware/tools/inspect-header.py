#!/usr/bin/env python3
"""Decode only a saved 24-byte Photon module_info_t; never opens USB or serial.

Layout: pinned Device OS dynalib/inc/module_info.h:53-79.
Bounds: hal/src/photon/ota_module_bounds.c:4-9.
Prefix offsets: linker_stm32f2xx_common.ld:193, part1_vtor_module.ld:10,
modules/photon/system-part2/module_system_part2_export.ld:10 and user.ld:7-12.
"""

import argparse
import json
from pathlib import Path
import struct


# name: module start, exclusive region end, prefix offset, function, index, minimum
COMPONENTS = {
    "bootloader": (0x08000000, 0x08004000, 0x184, 2, 0, 1003),
    "system1": (0x08020000, 0x08060000, 0x184, 4, 1, 2302),
    "system2": (0x08060000, 0x080A0000, 0x184, 4, 2, 2302),
    "user": (0x080A0000, 0x080C0000, 0, 5, 1, None),
}
FUNCTION_NAMES = {0: "none", 2: "bootloader", 3: "monolithic", 4: "system", 5: "user"}
HEADER = struct.Struct("<IIBBHHBBBBHBBH")
assert HEADER.size == 24


def addresses():
    return {
        name: {
            "module_start": f"0x{values[0]:08x}",
            "prefix_offset": f"0x{values[2]:x}",
            "read_address": f"0x{values[0] + values[2]:08x}",
            "read_length": HEADER.size,
        }
        for name, values in COMPONENTS.items()
    }


def decode(component, data):
    if len(data) != HEADER.size:
        raise ValueError(f"Expected exactly 24 bytes, received {len(data)}; no whole-flash dump is needed")
    (start, end, reserved, flags, version, platform, function, index,
     dep_func, dep_index, dep_version, dep2_func, dep2_index, dep2_version) = HEADER.unpack(data)
    expected_start, region_end, offset, expected_func, expected_index, minimum = COMPONENTS[component]
    if platform != 6 or function != expected_func or index != expected_index or start != expected_start:
        raise ValueError("Header does not identify the expected original-Photon modular component; stop rather than guessing another flash location")
    if not start + offset + HEADER.size <= end <= region_end - 4:
        raise ValueError("Module end is outside its authoritative flash region (including final CRC)")
    dependencies = []
    for dep_function, dep_number, dep_minimum in (
        (dep_func, dep_index, dep_version), (dep2_func, dep2_index, dep2_version)
    ):
        if dep_function:
            dependencies.append({
                "function": dep_function,
                "type": FUNCTION_NAMES.get(dep_function, "unknown"),
                "index": dep_number,
                "minimum_module_version": dep_minimum,
            })
    return {
        "component": component,
        "header_address": f"0x{expected_start + offset:08x}",
        "header_bytes": HEADER.size,
        "module_start": f"0x{start:08x}",
        "module_end_exclusive_before_crc": f"0x{end:08x}",
        "module_bytes_including_crc": end - start + 4,
        "platform_id": platform,
        "function": function,
        "index": index,
        "module_version": version,
        "reserved": reserved,
        "flags": flags,
        "dependencies": dependencies,
        "pi_light_minimum_module_version": minimum,
        "minimum_version_satisfied": None if minimum is None else version >= minimum,
        "integrity": "not_checked_header_only",
        "note": "Version/dependency metadata only; this read cannot verify CRC, authenticity or executability",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=COMPONENTS, nargs="?")
    parser.add_argument("file", type=Path, nargs="?")
    parser.add_argument("--addresses", action="store_true", help="Print source-backed 24-byte read locations without hardware access")
    args = parser.parse_args()
    if args.addresses:
        if args.component or args.file:
            parser.error("--addresses takes no component or file")
        result = addresses()
    else:
        if not args.component or not args.file:
            parser.error("provide COMPONENT FILE, or --addresses")
        try:
            with args.file.open("rb") as saved_header:
                data = saved_header.read(HEADER.size + 1)
            result = decode(args.component, data)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
