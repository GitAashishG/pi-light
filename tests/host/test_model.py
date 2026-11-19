import unittest

from host.model import (LEASE_SECONDS, MAX_SESSIONS, MAX_TOMBSTONES, RequestError,
                        Sessions, TOMBSTONE_SECONDS, validate_request)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def update(session, sequence, state):
    return {"op": "update", "session": session, "seq": sequence, "state": state}


def remove(session, sequence):
    return {"op": "remove", "session": session, "seq": sequence}


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sessions = Sessions(self.clock)

    def test_precedence_and_independent_removal(self):
        for state in ("idle", "done", "working", "error", "waiting"):
            self.assertEqual(self.sessions.apply(update(state, 1, state))["aggregate"], state)
        for state, expected in (("waiting", "error"), ("error", "working"),
                                ("working", "done"), ("done", "idle"), ("idle", "idle")):
            self.assertEqual(self.sessions.apply(remove(state, 2))["aggregate"], expected)
        self.assertEqual(self.sessions.summary(), {"ok": True, "aggregate": "idle", "sessions": 0})

    def test_expiry_uses_monotonic_deadline_without_events(self):
        self.sessions.apply(update("one", 1, "waiting"))
        self.clock.advance(LEASE_SECONDS - 0.001)
        self.assertEqual(self.sessions.summary()["aggregate"], "waiting")
        self.clock.advance(0.001)
        self.assertEqual(self.sessions.summary()["aggregate"], "idle")
        with self.assertRaisesRegex(RequestError, "stale-sequence"):
            self.sessions.apply(update("one", 1, "working"))
        self.sessions.apply(update("one", 2, "done"))
        self.assertEqual(self.sessions.summary()["aggregate"], "done")

    def test_duplicate_and_reordered_updates_do_not_renew_lease(self):
        self.sessions.apply(update("one", 8, "working"))
        self.clock.advance(10)
        for sequence in (8, 7, 0):
            with self.assertRaisesRegex(RequestError, "stale-sequence"):
                self.sessions.apply(update("one", sequence, "waiting"))
        self.clock.advance(2)
        self.assertEqual(self.sessions.summary()["sessions"], 0)

    def test_ordered_removes_and_tombstones(self):
        self.sessions.apply(update("one", 10, "waiting"))
        for sequence in (9, 10):
            with self.assertRaisesRegex(RequestError, "stale-sequence"):
                self.sessions.apply(remove("one", sequence))
        self.assertEqual(self.sessions.apply(remove("one", 12))["sessions"], 0)
        for request in (update("one", 11, "working"), remove("one", 12)):
            with self.assertRaisesRegex(RequestError, "stale-sequence"):
                self.sessions.apply(request)
        self.sessions.apply(update("one", 13, "done"))
        self.assertEqual(self.sessions.summary()["aggregate"], "done")

    def test_remove_before_update_prevents_revival(self):
        self.sessions.apply(remove("not-yet-seen", 2))
        with self.assertRaisesRegex(RequestError, "stale-sequence"):
            self.sessions.apply(update("not-yet-seen", 1, "working"))

    def test_tombstones_are_bounded_and_short_lived(self):
        for index in range(MAX_TOMBSTONES + 20):
            self.sessions.apply(remove(str(index), 1))
        self.assertEqual(len(self.sessions.tombstones), MAX_TOMBSTONES)
        self.clock.advance(TOMBSTONE_SECONDS)
        self.sessions.expire()
        self.assertEqual(len(self.sessions.tombstones), 0)

    def test_session_limit_allows_existing_publisher_and_releases_capacity(self):
        for index in range(MAX_SESSIONS):
            self.sessions.apply(update(str(index), 1, "working"))
        with self.assertRaisesRegex(RequestError, "session-limit"):
            self.sessions.apply(update("excess", 1, "waiting"))
        self.sessions.apply(update("0", 2, "waiting"))
        self.sessions.apply(remove("0", 3))
        self.sessions.apply(update("excess", 1, "error"))
        self.assertEqual(self.sessions.summary()["sessions"], MAX_SESSIONS)

    def test_strict_schema(self):
        invalid = [None, [], {}, {"op": []}, {"op": "status", "extra": 1},
                   {"op": "shutdown", "pid": 1}, {"op": "query", "state": "idle"},
                   update("", 1, "idle"), update("a/b", 1, "idle"), update("é", 1, "idle"),
                   update("a" * 129, 1, "idle"), update("one", True, "idle"),
                   update("one", -1, "idle"), update("one", 1 << 53, "idle"),
                   update("one", 1.0, "idle"), update("one", 1, "offline"),
                   update("one", 1, ["working"])]
        for request in invalid:
            with self.subTest(request=request), self.assertRaisesRegex(RequestError, "invalid-request"):
                validate_request(request)
        for operation in ("status", "shutdown", "query"):
            self.assertEqual(validate_request({"op": operation}), operation)


if __name__ == "__main__":
    unittest.main()
