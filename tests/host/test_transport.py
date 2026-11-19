from collections import deque
import threading
from types import SimpleNamespace
import unittest

from host.transport import (FRAME_TIMEOUT, Frames, HEARTBEAT_SECONDS, IO_TIMEOUT, MAX_LINE,
                            MAX_QUERIES, PHOTON_PID, PHOTON_VID, RECONNECT_SECONDS,
                            SerialOwner, TransportError, WRITE_TIMEOUT, parse_ack,
                            parse_hello, select_port)


class Clock:
    def __init__(self):
        self.now = 100.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.now

    def advance(self, seconds):
        with self.lock:
            self.now += seconds


class ScriptedSerial:
    """Isolated in-memory USB peer, injected only through the transport constructor."""

    def __init__(self, clock, respond=True, hello=True):
        self.clock = clock
        self.respond = respond
        self.hello = hello
        self.writes = []
        self.pending = deque()
        self.closed = threading.Event()
        self.state_seen = threading.Event()
        self.heartbeat_seen = threading.Event()
        self.fail = False
        self.state = "offline"
        self.state_count = 0
        self.last_state_time = None
        self.mutex = threading.Lock()

    def write(self, payload):
        with self.mutex:
            self.writes.append(payload)
            if self.fail:
                raise OSError("private device error must not escape")
            if payload == b"HELLO\n" and self.hello:
                self.pending.append(b"PI-LIGHT 1 abcdef0123456789abcdef01\n")
            elif payload.startswith(b"PI1 ") and self.respond:
                _, sequence, state, _ = payload.decode("ascii").split()
                self.state = state
                self.last_state_time = self.clock()
                self.state_count += 1
                self.pending.append(f"PI1 {sequence} {state} 0 0 48\n".encode("ascii"))
                self.state_seen.set()
                if self.state_count >= 2:
                    self.heartbeat_seen.set()
            elif payload.startswith(b"PI1? ") and self.respond:
                sequence = payload.decode("ascii").split()[1]
                self.pending.append(f"PI1 {sequence} {self.state} 0 0 48\n".encode("ascii"))
            return len(payload)

    def read(self, size):
        self.clock.advance(IO_TIMEOUT)
        with self.mutex:
            if self.fail:
                raise OSError("private device error must not escape")
            if not self.pending:
                return b""
            data = self.pending.popleft()
            if len(data) > size:
                self.pending.appendleft(data[size:])
            return data[:size]

    def close(self):
        self.closed.set()


class ParsingTests(unittest.TestCase):
    def test_exact_hello_and_ack_validation(self):
        self.assertEqual(parse_hello(b"PI-LIGHT 1 012345abcdef\n"), "012345abcdef")
        for value in (b"PI-LIGHT 2 id\n", b"PI-LIGHT 1 \n", b"PI-LIGHT 1 private text\n",
                      b"PI-LIGHT 1 id\r\n", b"PI-LIGHT 1 " + b"a" * 65 + b"\n"):
            self.assertIsNone(parse_hello(value))
        self.assertEqual(parse_ack(b"PI1 4294967295 offline 0 128 255\n"),
                         (4294967295, "offline", [0, 128, 255]))
        for value in (b"PI1 4294967296 idle 1 2 3\n", b"PI1 -1 idle 1 2 3\n",
                      b"PI1 1 other 1 2 3\n", b"PI1 1 waiting 256 0 0\n",
                      b"PI1 1 waiting 0 -1 0\n", b"PI1 1 waiting 0 1 0 extra\n",
                      b"PI1 1 waiting 0 1 0\r\n", b"PI1 1 waiting 0 1 0"):
            self.assertIsNone(parse_ack(value))

    def test_fragmentation_and_oversize_resynchronization(self):
        frames = Frames()
        self.assertEqual(frames.feed(b"PI-LI"), [])
        self.assertEqual(frames.feed(b"GHT 1 id\n"), [b"PI-LIGHT 1 id\n"])
        self.assertEqual(frames.feed(b"x" * (MAX_LINE + 1)), [])
        self.assertLessEqual(len(frames.buffer), MAX_LINE)
        self.assertEqual(frames.feed(b"PI-LIGHT 1 forged\nPI-LIGHT 1 real\n"), [b"PI-LIGHT 1 real\n"])

    def test_only_unique_original_photon_is_discovered(self):
        def port(device, vid, pid):
            return SimpleNamespace(device=device, vid=vid, pid=pid)
        photon = port("/fake/photon", PHOTON_VID, PHOTON_PID)
        dfu = port("/fake/dfu", PHOTON_VID, 0xD006)
        esp32 = port("/fake/esp32", 0x10C4, 0xEA60)
        self.assertIsNone(select_port([dfu, esp32]))
        self.assertEqual(select_port([dfu, esp32, photon]), photon.device)
        self.assertIsNone(select_port([photon, port("/fake/second", PHOTON_VID, PHOTON_PID)]))
        self.assertIsNone(select_port([esp32], esp32.device))
        self.assertIsNone(select_port([dfu], dfu.device))
        self.assertEqual(select_port([], "/fake/unlisted-diagnostic"), "/fake/unlisted-diagnostic")


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.owner = SerialOwner(clock=self.clock)

    def test_ack_correlation_and_actual_effective_state(self):
        peer = ScriptedSerial(self.clock, respond=False)
        peer.pending.extend([b"garbage\n", b"PI1 999 waiting 1 2 3\n", b"PI1 1 working 0 0 42\n"])
        result = self.owner._exchange(peer, Frames(), "working")
        self.assertEqual(result["state"], "working")
        self.assertEqual(result["rgb"], [0, 0, 42])
        self.assertEqual(result["last_ack_age_s"], 0)
        self.assertEqual(peer.writes, [b"PI1 1 working 48\n"])
        self.owner.set_desired("waiting")
        self.assertEqual(self.owner.snapshot()["state"], "working")
        self.clock.advance(2)
        self.assertEqual(self.owner.snapshot()["last_ack_age_s"], 2)

    def test_wrong_ack_or_wrong_effective_state_times_out_without_fabrication(self):
        peer = ScriptedSerial(self.clock, respond=False)
        peer.pending.extend([b"PI1 99 waiting 1 2 3\n", b"PI1 1 done 1 2 3\n"])
        started = self.clock()
        with self.assertRaisesRegex(TransportError, "device-timeout"):
            self.owner._exchange(peer, Frames(), "waiting")
        self.assertLessEqual(self.clock() - started, FRAME_TIMEOUT + IO_TIMEOUT + 0.001)
        self.assertIsNone(self.owner.snapshot()["state"])
        self.assertIsNone(self.owner.snapshot()["rgb"])
        self.assertIsNone(self.owner.snapshot()["last_ack_age_s"])

    def test_query_is_correlated_and_never_heartbeats(self):
        peer = ScriptedSerial(self.clock)
        peer.state = "offline"
        result = self.owner._exchange(peer, Frames())
        self.assertEqual(result["state"], "offline")
        self.assertEqual(peer.writes, [b"PI1? 1\n"])
        self.assertIsNone(peer.last_state_time)

    def test_uint32_sequence_wrap_and_short_write(self):
        self.owner.sequence = 0xFFFFFFFF
        peer = ScriptedSerial(self.clock)
        self.owner._exchange(peer, Frames(), "idle")
        self.assertEqual(peer.writes, [b"PI1 0 idle 48\n"])
        peer.write = lambda payload: len(payload) - 1
        with self.assertRaisesRegex(TransportError, "short-write"):
            self.owner._exchange(peer, Frames(), "working")

    def test_query_bounds_and_disconnected_error(self):
        result = self.owner.query()
        self.assertTrue(result.finished.is_set())
        self.assertEqual(result.error, "device-unavailable")
        self.owner.connected = True
        for _ in range(MAX_QUERIES):
            self.assertFalse(self.owner.query().finished.is_set())
        self.assertEqual(self.owner.query().error, "server-busy")
        self.owner._finish_queries("device-unavailable")
        self.assertEqual(len(self.owner.queries), 0)


class SerialLifecycleTests(unittest.TestCase):
    def make_owner(self, clock, factory, inventory):
        owner = SerialOwner(serial_factory=factory, list_ports=lambda: list(inventory), clock=clock)
        self.addCleanup(owner.stop)
        return owner

    def test_no_state_before_successful_hello(self):
        clock = Clock()
        peer = ScriptedSerial(clock, hello=False)
        inventory = [SimpleNamespace(device="/fake/photon", vid=PHOTON_VID, pid=PHOTON_PID)]
        owner = self.make_owner(clock, lambda **kwargs: peer, inventory)
        owner.set_desired("waiting")
        owner.start()
        self.assertTrue(peer.closed.wait(1), "handshake failure did not close the port")
        owner.stop()
        self.assertFalse(owner.thread.is_alive())
        self.assertEqual(peer.writes, [b"HELLO\n"])
        self.assertFalse(owner.snapshot()["connected"])
        self.assertIsNone(owner.snapshot()["id"])

    def test_handshake_heartbeat_query_disconnect_replug_and_idle_shutdown(self):
        clock = Clock()
        first = ScriptedSerial(clock)
        second = ScriptedSerial(clock)
        calls = []
        inventory = [SimpleNamespace(device="/fake/photon-a", vid=PHOTON_VID, pid=PHOTON_PID)]

        def factory(**kwargs):
            calls.append(kwargs)
            return first if kwargs["port"] == "/fake/photon-a" else second

        owner = self.make_owner(clock, factory, inventory)
        owner.set_desired("waiting")
        owner.start()
        self.assertTrue(first.state_seen.wait(1))
        # A query completion is an ordering barrier for the initial ACK.
        initial = owner.query()
        self.assertTrue(initial.finished.wait(1))
        self.assertIsNone(initial.error)
        self.assertEqual(initial.device["state"], "waiting")
        self.assertEqual(initial.device["id"], "abcdef0123456789abcdef01")
        self.assertEqual(first.writes[0], b"HELLO\n")
        self.assertEqual(calls[0]["timeout"], IO_TIMEOUT)
        self.assertEqual(calls[0]["write_timeout"], WRITE_TIMEOUT)
        self.assertTrue(calls[0]["exclusive"])
        previous_state_time = first.last_state_time
        queried = owner.query()
        self.assertTrue(queried.finished.wait(1))
        self.assertEqual(first.last_state_time, previous_state_time)
        clock.advance(HEARTBEAT_SECONDS)
        self.assertTrue(first.heartbeat_seen.wait(1), "periodic heartbeat required no new publisher update")
        # Force the next query transaction to fail; its completion confirms disconnection.
        first.fail = True
        broken = owner.query()
        self.assertTrue(broken.finished.wait(1))
        self.assertIn(broken.error, ("device-timeout", "device-unavailable"))
        self.assertFalse(owner.snapshot()["connected"])
        self.assertTrue(first.closed.wait(1))
        inventory[:] = [SimpleNamespace(device="/fake/photon-b", vid=PHOTON_VID, pid=PHOTON_PID)]
        clock.advance(RECONNECT_SECONDS + 0.1)
        owner.wake.set()
        self.assertTrue(second.state_seen.wait(1), "replug did not reconnect")
        reconnected = owner.query()
        self.assertTrue(reconnected.finished.wait(1))
        self.assertIsNone(reconnected.error)
        self.assertTrue(reconnected.device["connected"])
        self.assertEqual(second.writes[0], b"HELLO\n")
        self.assertEqual(len(calls), 2)
        owner.stop()
        self.assertFalse(owner.thread.is_alive())
        self.assertEqual(second.state, "idle")
        self.assertTrue(second.closed.is_set())
        self.assertFalse(owner.snapshot()["connected"])

    def test_missing_and_ambiguous_hardware_never_open_a_port(self):
        clock = Clock()
        inspected = threading.Event()
        opened = []
        inventory = [SimpleNamespace(device="/fake/one", vid=PHOTON_VID, pid=PHOTON_PID),
                     SimpleNamespace(device="/fake/two", vid=PHOTON_VID, pid=PHOTON_PID)]

        def ports():
            inspected.set()
            return inventory

        owner = SerialOwner(serial_factory=lambda **kwargs: opened.append(kwargs), list_ports=ports, clock=clock)
        self.addCleanup(owner.stop)
        owner.start()
        self.assertTrue(inspected.wait(1))
        owner.stop()
        self.assertEqual(opened, [])
        self.assertFalse(owner.snapshot()["connected"])
        self.assertEqual(owner.query().error, "device-unavailable")


if __name__ == "__main__":
    unittest.main()
