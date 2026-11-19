from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from host.bridge import (AlreadyRunning, MAX_CLIENTS, MAX_REQUEST, OwnershipError,
                         QUERY_TIMEOUT, Runtime, Server, decode_request, main, request,
                         validate_response)
from host.model import RequestError


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeTransport:
    def __init__(self):
        self.desired = "idle"
        self.idle = threading.Event()
        self.idle.set()
        self.device = {"connected": False, "id": None, "state": None, "rgb": None,
                       "last_ack_age_s": None}
        self.pending = []

    def set_desired(self, state):
        self.desired = state
        if state == "idle":
            self.idle.set()
        else:
            self.idle.clear()

    def snapshot(self):
        return dict(self.device)

    def query(self):
        result = SimpleNamespace(finished=threading.Event(), device=None, error=None)
        self.pending.append(result)
        return result


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pi-light-")
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / "state"
        self.runtime = None

    def tearDown(self):
        if self.runtime:
            self.runtime.close()
        self.temporary.cleanup()

    def test_permissions_duplicate_refusal_and_owned_cleanup(self):
        self.runtime = Runtime(self.path).acquire()
        socket_inode = (self.path / "bridge.sock").stat().st_ino
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.path / "bridge.sock").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.path / "bridge.lock").stat().st_mode), 0o600)
        with self.assertRaises(AlreadyRunning):
            Runtime(self.path).acquire()
        self.assertEqual((self.path / "bridge.sock").stat().st_ino, socket_inode)
        self.runtime.close()
        self.assertFalse((self.path / "bridge.sock").exists())
        self.assertFalse((self.path / "bridge.lock").exists())
        self.runtime = Runtime(self.path).acquire()

    def test_stale_socket_removed_only_after_ownership(self):
        self.path.mkdir(mode=0o700)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.path / "bridge.sock"))
        stale.close()
        (self.path / "bridge.lock").write_text("999999\n")
        self.runtime = Runtime(self.path).acquire()
        self.assertTrue((self.path / "bridge.sock").exists())

    def test_live_socket_without_our_lock_is_preserved(self):
        self.path.mkdir(mode=0o700)
        live = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        live.bind(str(self.path / "bridge.sock"))
        live.listen(1)
        try:
            inode = (self.path / "bridge.sock").stat().st_ino
            with self.assertRaises(AlreadyRunning):
                Runtime(self.path).acquire()
            self.assertEqual((self.path / "bridge.sock").stat().st_ino, inode)
        finally:
            live.close()

    def test_symlink_directory_and_ancestor_are_rejected(self):
        target = self.root / "real"
        target.mkdir()
        self.path.symlink_to(target, target_is_directory=True)
        with self.assertRaises(OwnershipError):
            Runtime(self.path).acquire()
        with self.assertRaises(OwnershipError):
            Runtime(self.path / "child").acquire()
        self.assertFalse((target / "bridge.sock").exists())

    def test_symlink_socket_and_metadata_are_never_removed(self):
        self.path.mkdir(mode=0o700)
        target = self.root / "keep"
        target.write_text("unrelated")
        for name in ("bridge.sock", "bridge.lock"):
            link = self.path / name
            link.symlink_to(target)
            with self.assertRaises(OwnershipError):
                Runtime(self.path).acquire()
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_text(), "unrelated")
            link.unlink()

    def test_unrelated_resource_and_hardlink_are_preserved(self):
        self.path.mkdir(mode=0o700)
        resource = self.path / "bridge.sock"
        resource.write_text("unrelated")
        with self.assertRaises(OwnershipError):
            Runtime(self.path).acquire()
        self.assertEqual(resource.read_text(), "unrelated")
        resource.unlink()
        target = self.root / "keep"
        target.write_text("123\n")
        os.link(target, self.path / "bridge.lock")
        with self.assertRaises(OwnershipError):
            Runtime(self.path).acquire()
        self.assertEqual(target.read_text(), "123\n")

    def test_unowned_directory_and_socket_are_rejected(self):
        actual_uid = os.getuid()
        self.path.mkdir(mode=0o700)
        with patch("host.bridge.os.getuid", return_value=actual_uid + 1):
            with self.assertRaises(OwnershipError):
                Runtime(self.path).acquire()
        self.runtime = Runtime(self.path).acquire()
        with patch("host.bridge.os.getuid", return_value=actual_uid + 1):
            with self.assertRaises(OwnershipError):
                self.runtime._existing("bridge.sock", socket_file=True)

    def test_cleanup_does_not_unlink_replaced_resource(self):
        self.runtime = Runtime(self.path).acquire()
        resource = self.path / "bridge.sock"
        resource.unlink()
        resource.write_text("replacement")
        self.runtime.close()
        self.assertEqual(resource.read_text(), "replacement")

    def test_invalid_metadata_is_not_treated_as_our_file(self):
        self.path.mkdir(mode=0o700)
        metadata = self.path / "bridge.lock"
        metadata.write_text("unrelated data")
        with self.assertRaises(OwnershipError):
            Runtime(self.path).acquire()
        self.assertEqual(metadata.read_text(), "unrelated data")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pi-light-")
        self.path = Path(self.temporary.name).resolve() / "state"
        self.runtime = Runtime(self.path).acquire()
        self.transport = FakeTransport()
        self.clock = Clock()
        self.server = Server(self.runtime, self.transport, self.clock)
        self.failure = []

        def run():
            try:
                self.server.run()
            except BaseException as error:
                self.failure.append(error)
            finally:
                self.runtime.close()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown_deadline = self.clock.now - 1
        self.server.should_stop = True
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive(), "server did not stop")
        self.runtime.close()
        self.temporary.cleanup()
        if self.failure:
            raise self.failure[0]

    def send(self, payload):
        return request(self.path, payload)

    def test_consumer_visible_aggregation_expiry_and_stale_remove(self):
        self.assertEqual(self.send({"op": "update", "session": "main", "seq": 1, "state": "working"}),
                         {"ok": True, "aggregate": "working", "sessions": 1})
        self.send({"op": "update", "session": "other", "seq": 1, "state": "waiting"})
        self.assertEqual(self.send({"op": "status"})["aggregate"], "waiting")
        self.assertEqual(self.send({"op": "remove", "session": "other", "seq": 0}),
                         {"ok": False, "error": "stale-sequence"})
        self.send({"op": "remove", "session": "other", "seq": 2})
        self.assertEqual(self.send({"op": "status"})["aggregate"], "working")
        self.clock.now += 12
        self.assertTrue(self.transport.idle.wait(1), "expiry did not run without an event")
        self.assertEqual(self.send({"op": "status"})["sessions"], 0)

    def test_desired_is_distinct_from_acknowledged_and_status_is_cached(self):
        self.transport.device.update(connected=True, id="device-123", state="working",
                                     rgb=[0, 0, 20], last_ack_age_s=1.0)
        self.send({"op": "update", "session": "main", "seq": 1, "state": "waiting"})
        result = self.send({"op": "status"})
        self.assertEqual(result["aggregate"], "waiting")
        self.assertEqual(result["device"]["state"], "working")
        self.assertEqual(result["device"]["rgb"], [0, 0, 20])
        self.assertEqual(self.transport.pending, [])

    def test_query_wait_does_not_block_status_and_returns_fresh_ack(self):
        query_client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        query_client.settimeout(2)
        query_client.connect(str(self.path / "bridge.sock"))
        query_client.sendall(b'{"op":"query"}\n')
        # A second local request is a server-side ordering barrier.
        for _ in range(10):
            self.assertTrue(self.send({"op": "status"})["ok"])
            if self.transport.pending:
                break
        self.assertEqual(len(self.transport.pending), 1)
        fresh = {"connected": True, "id": "device-123", "state": "offline",
                 "rgb": [1, 1, 1], "last_ack_age_s": 0.0}
        pending = self.transport.pending[0]
        pending.device = fresh
        pending.finished.set()
        try:
            result = json.loads(query_client.recv(MAX_REQUEST))
        finally:
            query_client.close()
        self.assertEqual(result["device"], fresh)
        self.assertEqual(result["aggregate"], "idle")

    def test_query_timeout_is_error_not_cached_success(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(str(self.path / "bridge.sock"))
        client.sendall(b'{"op":"query"}\n')
        for _ in range(10):
            self.send({"op": "status"})
            if self.transport.pending:
                break
        self.assertEqual(len(self.transport.pending), 1)
        self.clock.now += QUERY_TIMEOUT
        try:
            self.assertEqual(json.loads(client.recv(MAX_REQUEST)), {"ok": False, "error": "device-timeout"})
        finally:
            client.close()

    def test_bad_requests_are_fixed_errors_and_connection_closes(self):
        for payload in (b'{"op":"status","prompt":"private"}\n', b'{"op":"status","op":"shutdown"}\n',
                        b'not-json\n', b'[' * 3000 + b'\n', b'x' * (MAX_REQUEST + 1)):
            with self.subTest(payload_length=len(payload)), socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(self.path / "bridge.sock"))
                client.sendall(payload)
                self.assertEqual(json.loads(client.recv(MAX_REQUEST)), {"ok": False, "error": "invalid-request"})
                self.assertEqual(client.recv(1), b"")
        self.assertTrue(self.send({"op": "status"})["ok"])

    def test_shutdown_reply_then_owned_cleanup(self):
        self.assertTrue(self.send({"op": "shutdown"})["ok"])
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.assertFalse((self.path / "bridge.sock").exists())
        self.assertFalse((self.path / "bridge.lock").exists())


class BoundsAndCliTests(unittest.TestCase):
    def test_parser_rejects_non_json_constants_and_multiple_lines(self):
        for payload in (b'{"op":"status"}\n{}\n', b'{"op":NaN}\n', b'{"op":"status"}', b'\xff\n'):
            with self.assertRaisesRegex(RequestError, "invalid-request"):
                decode_request(payload)

    def test_diagnostics_reject_arbitrary_fields_and_untrusted_errors(self):
        invalid = [{"ok": True, "aggregate": "idle", "sessions": 0, "private": "payload"},
                   {"ok": False, "error": "private-payload"},
                   {"ok": False, "error": "device-timeout", "private": "payload"},
                   {"ok": True, "aggregate": "idle", "sessions": True}]
        for response in invalid:
            with self.assertRaisesRegex(RequestError, "invalid-response"):
                validate_response(response, "update")
        base = {"ok": True, "aggregate": "idle", "sessions": 0,
                "device": {"connected": True, "id": "actual-id", "state": "idle",
                           "rgb": [1, 1, 1], "last_ack_age_s": 0.0}}
        self.assertEqual(validate_response(base, "status"), base)
        for key, value in (("id", "private text"), ("state", "private-text"),
                           ("rgb", [1, True, 3]), ("last_ack_age_s", float("inf"))):
            response = dict(base, device=dict(base["device"], **{key: value}))
            with self.assertRaisesRegex(RequestError, "invalid-response"):
                validate_response(response, "status")

    def test_partial_client_deadline_and_client_capacity_are_bounded(self):
        clock = Clock()
        transport = FakeTransport()
        with tempfile.TemporaryDirectory(prefix="pi-light-") as temporary:
            runtime = Runtime(Path(temporary).resolve() / "state").acquire()
            server = Server(runtime, transport, clock)
            peers = []
            try:
                for _ in range(MAX_CLIENTS + 1):
                    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    peer.settimeout(1)
                    peer.connect(str(runtime.path / "bridge.sock"))
                    peers.append(peer)
                    server._accept()
                self.assertEqual(len(server.clients), MAX_CLIENTS)
                clock.now += 2
                server._maintenance()
                for client in list(server.clients.values()):
                    server._write(client)
                self.assertEqual(len(server.clients), 0)
                self.assertEqual(json.loads(peers[0].recv(MAX_REQUEST)), {"ok": False, "error": "request-timeout"})
                self.assertEqual(json.loads(peers[-1].recv(MAX_REQUEST)), {"ok": False, "error": "server-busy"})
            finally:
                for peer in peers:
                    peer.close()
                for client in list(server.clients.values()):
                    server._close_client(client)
                server.selector.close()
                runtime.close()

    def test_cli_uses_same_leased_socket_operations(self):
        with patch("host.bridge.request", return_value={"ok": True, "aggregate": "idle", "sessions": 0}) as call:
            for arguments, expected in (
                (["notify", "waiting", "--session", "diagnostic-abc", "--seq", "1"],
                 {"op": "update", "state": "waiting", "session": "diagnostic-abc", "seq": 1}),
                (["remove", "--session", "diagnostic-abc", "--seq", "2"],
                 {"op": "remove", "session": "diagnostic-abc", "seq": 2}),
                (["query"], {"op": "query"}), (["stop"], {"op": "shutdown"})):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(arguments), 0)
                self.assertEqual(call.call_args.args[1], expected)

    def test_cli_argument_failure_does_not_echo_payload(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit) as failure:
            main(["notify", "private-payload", "--session", "id", "--seq", "1"])
        self.assertEqual(failure.exception.code, 2)
        self.assertNotIn("private-payload", output.getvalue())
        self.assertEqual(json.loads(output.getvalue()), {"ok": False, "error": "invalid-arguments"})


if __name__ == "__main__":
    unittest.main()
