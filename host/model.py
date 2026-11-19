"""Validated, monotonic session leases; no publisher payload is retained."""

from collections import OrderedDict
from dataclasses import dataclass
import re
import time

STATES = ("idle", "done", "working", "error", "waiting")
LEASE_SECONDS = 12.0
MAX_SESSIONS = 256
MAX_TOMBSTONES = 1024
TOMBSTONE_SECONDS = 60.0
MAX_SEQUENCE = (1 << 53) - 1
SESSION_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)


class RequestError(Exception):
    """Only fixed, public-safe messages may cross the socket boundary."""


def validate_request(request):
    if not isinstance(request, dict) or not isinstance(request.get("op"), str):
        raise RequestError("invalid-request")
    operation = request["op"]
    expected = {
        "update": {"op", "session", "seq", "state"},
        "remove": {"op", "session", "seq"},
        "status": {"op"},
        "query": {"op"},
        "shutdown": {"op"},
    }.get(operation)
    if expected is None or request.keys() != expected:
        raise RequestError("invalid-request")
    if operation in ("update", "remove"):
        session = request["session"]
        sequence = request["seq"]
        if not isinstance(session, str) or not SESSION_PATTERN.fullmatch(session):
            raise RequestError("invalid-request")
        if type(sequence) is not int or not 0 <= sequence <= MAX_SEQUENCE:
            raise RequestError("invalid-request")
    if operation == "update" and request["state"] not in STATES:
        raise RequestError("invalid-request")
    return operation


@dataclass(frozen=True)
class Lease:
    sequence: int
    state: str
    deadline: float


class Sessions:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.live = {}
        self.tombstones = OrderedDict()

    def _remember(self, session, sequence, now):
        self.tombstones.pop(session, None)
        self.tombstones[session] = (sequence, now + TOMBSTONE_SECONDS)
        while len(self.tombstones) > MAX_TOMBSTONES:
            self.tombstones.popitem(last=False)

    def expire(self):
        now = self.clock()
        for session, (_, deadline) in list(self.tombstones.items()):
            if deadline <= now:
                del self.tombstones[session]
        for session, lease in list(self.live.items()):
            if lease.deadline <= now:
                del self.live[session]
                self._remember(session, lease.sequence, now)

    def apply(self, request):
        operation = validate_request(request)
        self.expire()
        if operation not in ("update", "remove"):
            raise RequestError("invalid-request")
        session, sequence = request["session"], request["seq"]
        previous = self.live.get(session)
        watermark = previous.sequence if previous else self.tombstones.get(session, (-1, 0))[0]
        if sequence <= watermark:
            raise RequestError("stale-sequence")
        if operation == "update":
            if previous is None and len(self.live) >= MAX_SESSIONS:
                raise RequestError("session-limit")
            self.tombstones.pop(session, None)
            self.live[session] = Lease(sequence, request["state"], self.clock() + LEASE_SECONDS)
        else:
            self.live.pop(session, None)
            self._remember(session, sequence, self.clock())
        return self.summary()

    def summary(self):
        self.expire()
        aggregate = max((lease.state for lease in self.live.values()), key=STATES.index, default="idle")
        return {"ok": True, "aggregate": aggregate, "sessions": len(self.live)}
