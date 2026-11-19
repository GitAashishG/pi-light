import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("inspect_header", ROOT / "firmware/tools/inspect-header.py")
HEADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HEADER)


class HeaderTests(unittest.TestCase):
    def fixture(self, name, version, **changes):
        start, limit, offset, function, index, _ = HEADER.COMPONENTS[name]
        fields = dict(start=start, end=start + offset + 128, reserved=0, flags=0,
                      version=version, platform=6, function=function, index=index,
                      dep_function=0, dep_index=0, dep_version=0,
                      dep2_function=0, dep2_index=0, dep2_version=0)
        fields.update(changes)
        return HEADER.HEADER.pack(*fields.values())

    def test_exact_addresses(self):
        actual = HEADER.addresses()
        for name, address in (("bootloader", "0x08000184"), ("system1", "0x08020184"),
                              ("system2", "0x08060184"), ("user", "0x080a0000")):
            self.assertEqual(actual[name]["read_address"], address)
            self.assertEqual(actual[name]["read_length"], 24)

    def test_bootloader_threshold(self):
        for version in (1002, 1003, 1006):
            result = HEADER.decode("bootloader", self.fixture("bootloader", version))
            self.assertEqual(result["minimum_version_satisfied"], version >= 1003)
            self.assertEqual(result["integrity"], "not_checked_header_only")

    def test_dependencies(self):
        data = self.fixture("system2", 2302, dep_function=4, dep_index=1, dep_version=2302,
                            dep2_function=2, dep2_index=0, dep2_version=1003)
        result = HEADER.decode("system2", data)
        self.assertTrue(result["minimum_version_satisfied"])
        self.assertEqual(result["dependencies"], [
            {"function": 4, "type": "system", "index": 1, "minimum_module_version": 2302},
            {"function": 2, "type": "bootloader", "index": 0, "minimum_module_version": 1003},
        ])

    def test_rejects_wrong_module_or_range(self):
        for changes in (dict(platform=32), dict(function=3), dict(index=2), dict(start=0x08060000),
                        dict(end=0x08020010), dict(end=0x08060000)):
            with self.assertRaises(ValueError):
                HEADER.decode("system1", self.fixture("system1", 2302, **changes))
        for data in (b"", b"\x00" * 23, b"\x00" * 25, b"\xff" * 24):
            with self.assertRaises(ValueError):
                HEADER.decode("bootloader", data)


if __name__ == "__main__":
    unittest.main()
