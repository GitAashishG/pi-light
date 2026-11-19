#!/usr/bin/env python3
"""Private, foreground Unix JSONL bridge for the original Particle Photon."""

import argparse
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import stat
import time
from dataclasses import dataclass, field

if __package__:
    from .model import RequestError, Sessions, STATES, validate_request
    from .transport import SerialOwner
else:
    from model import RequestError, Sessions, STATES, validate_request
    from transport import SerialOwner

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "pi-light"
MAX_REQUEST = 4096
MAX_CLIENTS = 32
REQUEST_TIMEOUT = 1.5
QUERY_TIMEOUT = 1.5
CLIENT_TIMEOUT = 3.0
TICK_SECONDS = 0.1


class OwnershipError(Exception):
    pass


class AlreadyRunning(Exception):
    pass


def _identity(info):
    return info.st_dev, info.st_ino


def _secure_directory(path):
    path = Path(os.path.abspath(os.path.expanduser(path)))
    current = Path(path.anchor)
    info = current.lstat()
    for component in path.parts[1:]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise OwnershipError("unsafe-state-directory")
    if info.st_uid != os.getuid():
        raise OwnershipError("unsafe-state-directory")
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    if _identity(os.fstat(descriptor)) != _identity(info):
        os.close(descriptor)
        raise OwnershipError("unsafe-state-directory")
    return path, descriptor


class Runtime:
    """The directory flock stays stable while removable PID metadata comes and goes.

    Locking a file then unlinking it permits two owners on different inodes. A
    directory flock avoids that race, including at shutdown and duplicate launch.
    """

    def __init__(self, state_dir):
        self.state_dir = state_dir
        self.directory = None
        self.path = None
        self.listener = None
        self.metadata = None
        self.owned = {}
        self.locked = False

    def _existing(self, name, socket_file=False):
        try:
            info = os.stat(name, dir_fd=self.directory, follow_symlinks=False)
        except FileNotFoundError:
            return None
        valid_type = stat.S_ISSOCK(info.st_mode) if socket_file else stat.S_ISREG(info.st_mode)
        if info.st_uid != os.getuid() or not valid_type or (not socket_file and info.st_nlink != 1):
            raise OwnershipError("unsafe-state-resource")
        return info

    def _unlink_matching(self, name, identity):
        try:
            info = os.stat(name, dir_fd=self.directory, follow_symlinks=False)
            if info.st_uid == os.getuid() and _identity(info) == identity:
                os.unlink(name, dir_fd=self.directory)
        except FileNotFoundError:
            pass

    def acquire(self):
        try:
            self.path, self.directory = _secure_directory(self.state_dir)
            try:
                fcntl.flock(self.directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AlreadyRunning("already-running") from None
            self.locked = True
            os.fchmod(self.directory, 0o700)
            old_socket = self._existing("bridge.sock", socket_file=True)
            old_metadata = self._existing("bridge.lock")
            if old_metadata is not None:
                descriptor = os.open("bridge.lock", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.directory)
                try:
                    metadata = os.read(descriptor, 32)
                    if (_identity(os.fstat(descriptor)) != _identity(old_metadata)
                            or not metadata.endswith(b"\n") or not metadata[:-1].isdigit()
                            or not 1 <= len(metadata[:-1]) <= 20):
                        raise OwnershipError("unsafe-state-resource")
                finally:
                    os.close(descriptor)
            if old_socket is not None:
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    probe.settimeout(0.15)
                    probe.connect(str(self.path / "bridge.sock"))
                except OSError as error:
                    if error.errno not in (errno.ENOENT, errno.ECONNREFUSED):
                        raise OwnershipError("unsafe-state-resource") from None
                else:
                    raise AlreadyRunning("already-running")
                finally:
                    probe.close()
                self._unlink_matching("bridge.sock", _identity(old_socket))
            if old_metadata is not None:
                self._unlink_matching("bridge.lock", _identity(old_metadata))
            self.metadata = os.open("bridge.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                    0o600, dir_fd=self.directory)
            self.owned["bridge.lock"] = _identity(os.fstat(self.metadata))
            os.fchmod(self.metadata, 0o600)
            os.write(self.metadata, f"{os.getpid()}\n".encode("ascii"))
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(str(self.path / "bridge.sock"))
            self.owned["bridge.sock"] = _identity(self._existing("bridge.sock", socket_file=True))
            os.chmod(self.path / "bridge.sock", 0o600)
            self.listener.listen(MAX_CLIENTS)
            self.listener.setblocking(False)
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.directory is not None:
            if self.locked:
                for name, identity in self.owned.items():
                    self._unlink_matching(name, identity)
                self.owned.clear()
                if self.listener is not None:
                    self.listener.close()
                    self.listener = None
                if self.metadata is not None:
                    os.close(self.metadata)
                    self.metadata = None
                fcntl.flock(self.directory, fcntl.LOCK_UN)
                self.locked = False
            os.close(self.directory)
            self.directory = None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def decode_request(data):
    try:
        if len(data) > MAX_REQUEST or not data.endswith(b"\n") or b"\n" in data[:-1]:
            raise ValueError("invalid frame")
        request = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))
        validate_request(request)
        return request
    except (ValueError, UnicodeError, RecursionError, RequestError):
        raise RequestError("invalid-request") from None


def encode_response(response):
    return (json.dumps(response, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


@dataclass
class Client:
    connection: object
    deadline: float
    incoming: bytearray = field(default_factory=bytearray)
    outgoing: bytes = b""
    sent: int = 0
    query: object = None


class Server:
    def __init__(self, runtime, transport, clock=time.monotonic):
        self.runtime = runtime
        self.transport = transport
        self.clock = clock
        self.sessions = Sessions(clock)
        self.selector = selectors.DefaultSelector()
        self.clients = {}
        self.should_stop = False
        self.shutdown_deadline = None

    def _close_client(self, client):
        descriptor = client.connection.fileno()
        try:
            self.selector.unregister(client.connection)
        except (KeyError, ValueError):
            pass
        client.connection.close()
        self.clients.pop(descriptor, None)

    def _reply(self, client, response):
        client.query = None
        client.outgoing = encode_response(response)
        client.deadline = self.clock() + 1.0
        self.selector.modify(client.connection, selectors.EVENT_WRITE, client)

    def _summary(self, device=None):
        response = self.sessions.summary()
        response["device"] = self.transport.snapshot() if device is None else device
        return response

    def _dispatch(self, client, request):
        operation = request["op"]
        if operation in ("update", "remove"):
            response = self.sessions.apply(request)
            self.transport.set_desired(response["aggregate"])
            self._reply(client, response)
        elif operation == "status":
            self._reply(client, self._summary())
        elif operation == "query":
            client.query = self.transport.query()
            client.deadline = self.clock() + QUERY_TIMEOUT
            # No polling a readable socket while the serial owner does its work.
            self.selector.unregister(client.connection)
        else:
            self._reply(client, self.sessions.summary())
            self.should_stop = True

    def _accept(self):
        for _ in range(8):
            try:
                connection, _ = self.runtime.listener.accept()
            except BlockingIOError:
                break
            connection.setblocking(False)
            if len(self.clients) >= MAX_CLIENTS:
                try:
                    connection.send(b'{"ok":false,"error":"server-busy"}\n')
                except OSError:
                    pass
                connection.close()
                continue
            client = Client(connection, self.clock() + REQUEST_TIMEOUT)
            self.clients[connection.fileno()] = client
            self.selector.register(connection, selectors.EVENT_READ, client)

    def _read(self, client):
        try:
            data = client.connection.recv(MAX_REQUEST + 1 - len(client.incoming))
            if not data:
                self._close_client(client)
                return
            client.incoming.extend(data)
            if len(client.incoming) > MAX_REQUEST:
                raise RequestError("invalid-request")
            if b"\n" in client.incoming:
                self._dispatch(client, decode_request(bytes(client.incoming)))
        except RequestError as error:
            self._reply(client, {"ok": False, "error": str(error)})
        except (ConnectionError, OSError):
            self._close_client(client)

    def _write(self, client):
        try:
            count = client.connection.send(client.outgoing[client.sent:])
            if count == 0:
                self._close_client(client)
                return
            client.sent += count
            if client.sent == len(client.outgoing):
                self._close_client(client)
        except BlockingIOError:
            pass
        except OSError:
            self._close_client(client)

    def _maintenance(self):
        self.transport.set_desired(self.sessions.summary()["aggregate"])
        for client in list(self.clients.values()):
            if client.query is not None and (client.query.finished.is_set() or self.clock() >= client.deadline):
                query = client.query
                response = ({"ok": False, "error": query.error or "device-timeout"}
                            if not query.finished.is_set() or query.error else self._summary(query.device))
                self.selector.register(client.connection, selectors.EVENT_WRITE, client)
                self._reply(client, response)
            elif self.clock() >= client.deadline:
                if client.outgoing:
                    self._close_client(client)
                else:
                    self._reply(client, {"ok": False, "error": "request-timeout"})

    def run(self):
        self.selector.register(self.runtime.listener, selectors.EVENT_READ, None)
        try:
            while True:
                self._maintenance()
                if self.should_stop:
                    if self.shutdown_deadline is None:
                        self.shutdown_deadline = self.clock() + 0.3
                        self.selector.unregister(self.runtime.listener)
                    if not self.clients or self.clock() >= self.shutdown_deadline:
                        break
                for key, mask in self.selector.select(TICK_SECONDS):
                    if key.data is None:
                        self._accept()
                    elif mask & selectors.EVENT_READ:
                        self._read(key.data)
                    else:
                        self._write(key.data)
        finally:
            for client in list(self.clients.values()):
                self._close_client(client)
            self.selector.close()


def _client_path(state_dir):
    # Client commands never create directories or repair permissions.
    path = Path(os.path.abspath(os.path.expanduser(state_dir)))
    current = Path(path.anchor)
    info = current.lstat()
    for component in path.parts[1:]:
        current = current / component
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise OwnershipError("unsafe-state-directory")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise OwnershipError("unsafe-state-directory")
    info = (path / "bridge.sock").lstat()
    if info.st_uid != os.getuid() or not stat.S_ISSOCK(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise OwnershipError("unsafe-state-resource")
    return path / "bridge.sock"


def validate_response(response, operation):
    invalid = RequestError("invalid-response")
    if not isinstance(response, dict) or type(response.get("ok")) is not bool:
        raise invalid
    if not response["ok"]:
        errors = ("invalid-request", "stale-sequence", "session-limit", "server-busy",
                  "device-unavailable", "device-timeout", "request-timeout")
        if response.keys() != {"ok", "error"} or response["error"] not in errors:
            raise invalid
        return response
    expected = {"ok", "aggregate", "sessions"}
    if operation in ("status", "query"):
        expected.add("device")
    if (response.keys() != expected or response["aggregate"] not in STATES
            or type(response["sessions"]) is not int or not 0 <= response["sessions"] <= 256):
        raise invalid
    if "device" in response:
        device = response["device"]
        if (not isinstance(device, dict)
                or device.keys() != {"connected", "id", "state", "rgb", "last_ack_age_s"}
                or type(device["connected"]) is not bool):
            raise invalid
        identifier, state, rgb, age = (device[key] for key in ("id", "state", "rgb", "last_ack_age_s"))
        if identifier is not None and (not isinstance(identifier, str)
                or re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", identifier, flags=re.ASCII) is None):
            raise invalid
        if device["connected"] and identifier is None:
            raise invalid
        if state is not None and state not in (*STATES, "offline"):
            raise invalid
        if rgb is not None and (not isinstance(rgb, list) or len(rgb) != 3
                or any(type(channel) is not int or not 0 <= channel <= 255 for channel in rgb)):
            raise invalid
        if age is not None and (type(age) not in (int, float)
                or (type(age) is float and not math.isfinite(age)) or age < 0):
            raise invalid
        if (state is None) != (rgb is None) or (state is None) != (age is None):
            raise invalid
    return response


def request(state_dir, payload):
    validate_request(payload)
    path = _client_path(state_dir)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(CLIENT_TIMEOUT)
        connection.connect(str(path))
        connection.sendall(encode_response(payload))
        response = bytearray()
        deadline = time.monotonic() + CLIENT_TIMEOUT
        while time.monotonic() < deadline:
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            data = connection.recv(MAX_REQUEST + 1 - len(response))
            if not data:
                break
            response.extend(data)
            if len(response) > MAX_REQUEST:
                raise RequestError("invalid-response")
            if b"\n" in response:
                try:
                    result = json.loads(response, object_pairs_hook=_unique_object)
                except (ValueError, UnicodeError, RecursionError):
                    raise RequestError("invalid-response") from None
                return validate_response(result, payload["op"])
    raise RequestError("bridge-unavailable")


class ArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, '{"ok":false,"error":"invalid-arguments"}\n')


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "status", "query", "stop", "notify", "remove"):
        command = commands.add_parser(name)
        command.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR), metavar="PATH")
        if name == "serve":
            command.add_argument("--port", help="explicit diagnostic port; still requires a Photon firmware hello")
            command.add_argument("--brightness", type=int, choices=range(129), default=48, metavar="0..128")
        if name == "notify":
            command.add_argument("state", choices=STATES)
        if name in ("notify", "remove"):
            command.add_argument("--session", required=True, help="opaque publisher ID, not a path or conversation text")
            command.add_argument("--seq", required=True, type=int)
    args = parser.parse_args(argv)
    runtime = None
    transport = None
    old_handlers = {}
    try:
        if args.command == "serve":
            runtime = Runtime(args.state_dir).acquire()
            transport = SerialOwner(args.port, args.brightness)
            server = Server(runtime, transport)
            for signum in (signal.SIGTERM, signal.SIGINT):
                old_handlers[signum] = signal.signal(signum, lambda _signum, _frame: setattr(server, "should_stop", True))
            transport.start()
            server.run()
            return 0
        payload = {"op": {"notify": "update", "stop": "shutdown"}.get(args.command, args.command)}
        if args.command in ("notify", "remove"):
            payload.update(session=args.session, seq=args.seq)
        if args.command == "notify":
            payload["state"] = args.state
        response = request(args.state_dir, payload)
        print(json.dumps(response, separators=(",", ":")))
        return 0 if response["ok"] else 1
    except AlreadyRunning:
        # Detached autostarts can race. Losing ownership is harmless.
        print('{"ok":true,"status":"already-running"}')
        return 0
    except RequestError as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")))
        return 1
    except OwnershipError:
        print('{"ok":false,"error":"unsafe-state-path"}')
        return 1
    except ImportError:
        print('{"ok":false,"error":"serial-dependency-unavailable"}')
        return 1
    except (OSError, ValueError):
        print('{"ok":false,"error":"bridge-unavailable"}')
        return 1
    finally:
        if transport is not None:
            transport.stop()
        if runtime is not None:
            runtime.close()
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
