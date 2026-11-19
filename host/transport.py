"""One bounded USB owner, independent of the Unix socket event loop."""

from collections import deque
import re
import threading
import time

if __package__:
    from .model import STATES
else:
    from model import STATES

PHOTON_VID = 0x2B04
PHOTON_PID = 0xC006
HEARTBEAT_SECONDS = 3.0
RECONNECT_SECONDS = 1.0
IO_TIMEOUT = 0.1
WRITE_TIMEOUT = 0.25
FRAME_TIMEOUT = 0.75
MAX_LINE = 96
MAX_QUERIES = 8
HELLO_PATTERN = re.compile(rb"PI-LIGHT 1 ([A-Za-z0-9._:-]{1,64})\n\Z")
ACK_PATTERN = re.compile(rb"PI1 ([0-9]{1,10}) (working|waiting|done|error|idle|offline) ([0-9]{1,3}) ([0-9]{1,3}) ([0-9]{1,3})\n\Z")


class TransportError(Exception):
    pass


def parse_hello(line):
    if len(line) > MAX_LINE:
        return None
    match = HELLO_PATTERN.fullmatch(line)
    return match[1].decode("ascii") if match else None


def parse_ack(line):
    if len(line) > MAX_LINE:
        return None
    match = ACK_PATTERN.fullmatch(line)
    if match is None:
        return None
    sequence = int(match[1])
    rgb = [int(match[index]) for index in (3, 4, 5)]
    if sequence > 0xFFFFFFFF or any(channel > 255 for channel in rgb):
        return None
    return sequence, match[2].decode("ascii"), rgb


def select_port(ports, explicit=None):
    """Never probe unrelated enumerated hardware, even with an explicit path."""
    ports = list(ports)
    if explicit is not None:
        matches = [port for port in ports if port.device == explicit]
        if matches and any((port.vid, port.pid) != (PHOTON_VID, PHOTON_PID) for port in matches):
            return None
        return explicit
    candidates = {port.device for port in ports if (port.vid, port.pid) == (PHOTON_VID, PHOTON_PID)}
    return next(iter(candidates)) if len(candidates) == 1 else None


class Frames:
    """Bound storage and discard an entire overlong line, not just its prefix."""

    def __init__(self):
        self.buffer = bytearray()
        self.discarding = False

    def feed(self, data):
        lines = []
        for byte in data:
            if self.discarding:
                if byte == 10:
                    self.discarding = False
                continue
            self.buffer.append(byte)
            if len(self.buffer) > MAX_LINE:
                self.buffer.clear()
                self.discarding = byte != 10
            elif byte == 10:
                lines.append(bytes(self.buffer))
                self.buffer.clear()
        return lines


class Query:
    def __init__(self, deadline):
        self.deadline = deadline
        self.finished = threading.Event()
        self.error = None
        self.device = None


class SerialOwner:
    def __init__(self, explicit_port=None, brightness=48, serial_factory=None, list_ports=None, clock=time.monotonic):
        self.explicit_port = explicit_port
        self.brightness = brightness
        self.serial_factory = serial_factory
        self.list_ports = list_ports
        self.clock = clock
        self.mutex = threading.Lock()
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.thread = None
        self.desired = "idle"
        self.connected = False
        self.device_id = None
        self.ack_state = None
        self.ack_rgb = None
        self.ack_time = None
        self.queries = deque()
        self.sequence = 0

    def start(self):
        if self.serial_factory is None or self.list_ports is None:
            import serial
            from serial.tools import list_ports
            self.serial_factory = self.serial_factory or serial.Serial
            self.list_ports = self.list_ports or list_ports.comports
        self.thread = threading.Thread(target=self._run, name="pi-light-usb", daemon=True)
        self.thread.start()

    def set_desired(self, state):
        if state not in STATES:
            raise ValueError("invalid state")
        with self.mutex:
            changed = self.desired != state
            self.desired = state
        if changed:
            self.wake.set()

    def snapshot(self):
        with self.mutex:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        return {
            "connected": self.connected,
            "id": self.device_id,
            "state": self.ack_state,
            "rgb": list(self.ack_rgb) if self.ack_rgb is not None else None,
            "last_ack_age_s": max(0.0, self.clock() - self.ack_time) if self.ack_time is not None else None,
        }

    def query(self):
        result = Query(self.clock() + FRAME_TIMEOUT + WRITE_TIMEOUT + 0.5)
        with self.mutex:
            if not self.connected or self.stopping.is_set():
                result.error = "device-unavailable"
                result.finished.set()
            elif len(self.queries) >= MAX_QUERIES:
                result.error = "server-busy"
                result.finished.set()
            else:
                self.queries.append(result)
                self.wake.set()
        return result

    def stop(self):
        self.stopping.set()
        self.wake.set()
        if self.thread is not None:
            # Current transaction and final idle each have bounded I/O deadlines.
            self.thread.join(2 * (FRAME_TIMEOUT + WRITE_TIMEOUT) + 1.0)

    def _next_sequence(self):
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        return self.sequence

    def _write(self, serial_port, payload):
        if serial_port.write(payload) != len(payload):
            raise TransportError("short-write")

    def _receive(self, serial_port, frames, parser, sequence=None, expected_state=None):
        deadline = self.clock() + FRAME_TIMEOUT
        while self.clock() < deadline:
            # A bounded read permits deadlines even if the device sends garbage forever.
            data = serial_port.read(MAX_LINE)
            for line in frames.feed(data):
                parsed = parser(line)
                if parsed is None:
                    continue
                if sequence is not None and parsed[0] != sequence:
                    continue
                if expected_state is not None and parsed[1] != expected_state:
                    continue
                return parsed
        raise TransportError("device-timeout")

    def _exchange(self, serial_port, frames, state=None):
        sequence = self._next_sequence()
        command = f"PI1? {sequence}\n" if state is None else f"PI1 {sequence} {state} {self.brightness}\n"
        self._write(serial_port, command.encode("ascii"))
        _, effective, rgb = self._receive(serial_port, frames, parse_ack, sequence, state)
        with self.mutex:
            self.ack_state, self.ack_rgb, self.ack_time = effective, rgb, self.clock()
            return self._snapshot_locked()

    def _finish_queries(self, error):
        with self.mutex:
            queries = list(self.queries)
            self.queries.clear()
        for query in queries:
            query.error = error
            query.finished.set()

    def _run(self):
        serial_port = None
        frames = None
        last_sent = None
        next_heartbeat = 0.0
        reconnect_at = 0.0
        try:
            while not self.stopping.is_set():
                self.wake.clear()
                if serial_port is None:
                    if self.clock() < reconnect_at:
                        self.wake.wait(min(0.25, reconnect_at - self.clock()))
                        continue
                    reconnect_at = self.clock() + RECONNECT_SECONDS
                    try:
                        port = select_port(self.list_ports(), self.explicit_port)
                        if port is None:
                            self.wake.wait(0.25)
                            continue
                        serial_port = self.serial_factory(port=port, baudrate=115200, timeout=IO_TIMEOUT,
                                                          write_timeout=WRITE_TIMEOUT, exclusive=True)
                        frames = Frames()
                        self._write(serial_port, b"HELLO\n")
                        device_id = self._receive(serial_port, frames, parse_hello)
                        with self.mutex:
                            self.connected = True
                            # History belongs to the handshaken device, never another board.
                            if self.device_id != device_id:
                                self.ack_state = self.ack_rgb = self.ack_time = None
                            self.device_id = device_id
                        last_sent = None
                        next_heartbeat = 0.0
                    except Exception:
                        if serial_port is not None:
                            try:
                                serial_port.close()
                            except Exception:
                                pass
                        serial_port = None
                        continue
                active_query = None
                try:
                    with self.mutex:
                        desired = self.desired
                    if desired != last_sent or self.clock() >= next_heartbeat:
                        next_heartbeat = self.clock() + HEARTBEAT_SECONDS
                        self._exchange(serial_port, frames, desired)
                        last_sent = desired
                    with self.mutex:
                        if self.queries:
                            active_query = self.queries.popleft()
                    if active_query is not None:
                        if self.clock() >= active_query.deadline:
                            active_query.error = "device-timeout"
                        else:
                            active_query.device = self._exchange(serial_port, frames)
                        active_query.finished.set()
                    self.wake.wait(max(0.0, min(0.1, next_heartbeat - self.clock())))
                except Exception:
                    reconnect_at = self.clock() + RECONNECT_SECONDS
                    with self.mutex:
                        self.connected = False
                    if active_query is not None:
                        active_query.error = "device-timeout"
                        active_query.finished.set()
                    self._finish_queries("device-unavailable")
                    try:
                        serial_port.close()
                    except Exception:
                        pass
                    serial_port = None
        finally:
            if serial_port is not None:
                try:
                    self._exchange(serial_port, frames, "idle")
                except Exception:
                    pass
                try:
                    serial_port.close()
                except Exception:
                    pass
            with self.mutex:
                self.connected = False
            self._finish_queries("device-unavailable")
