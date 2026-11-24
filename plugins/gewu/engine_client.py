"""A JSON-lines client for the Fignimble engine (`fignimble.rpc`) in a child process.

One request at a time per id; replies may come back in any order. `control`
carries GeWu's cancellation flag; cancelling sends the engine its own `cancel`
and waits for the request to settle instead of guessing.
"""

from __future__ import annotations

import itertools
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from gewu_plugin import ProtocolError

MAX_LINE = 16 * 1024 * 1024


class EngineClosed(ProtocolError):
    pass


class Engine:
    def __init__(self, python: Path, engine_root: Path, project: Path, cache: Path, on_event=None):
        env = dict(os.environ, PYTHONPATH=str(engine_root), PYTHONUNBUFFERED="1",
                   MPLBACKEND="Agg", PYTHONDONTWRITEBYTECODE="1")
        self.cache = cache
        self.log = (cache / "engine.log").open("ab")
        self.process = subprocess.Popen([str(python), "-u", "-m", "fignimble.rpc"], cwd=str(project),
                                        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log)
        self.serial = itertools.count(1)
        self.lock = threading.Lock()
        self.pending: dict[int, queue.Queue] = {}
        self.on_event = on_event
        self.closed = threading.Event()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while line := self.process.stdout.readline(MAX_LINE + 1):
                if not line.endswith(b"\n") or len(line) > MAX_LINE:
                    break
                try:
                    message = json.loads(line)
                except ValueError:
                    break
                if "id" in message:
                    with self.lock:
                        slot = self.pending.get(message["id"])
                    if slot is not None:
                        slot.put_nowait(message)
                elif message.get("event") and self.on_event:
                    self.on_event(message)
        except (OSError, ValueError):
            pass
        finally:
            self.closed.set()

    def request(self, command: str, *, timeout: float = 200, control=None, **params):
        ticket = queue.Queue(maxsize=1)
        with self.lock:
            if self.closed.is_set():
                raise EngineClosed("ENGINE_CLOSED", "the Fignimble engine is no longer running")
            request_id = next(self.serial)
            payload = json.dumps({"id": request_id, "cmd": command, **params}).encode() + b"\n"
            self.pending[request_id] = ticket
            try:
                self.process.stdin.write(payload)
                self.process.stdin.flush()
            except OSError as error:
                self.pending.pop(request_id, None)
                raise ProtocolError("OUTCOME_UNKNOWN",
                                    "the engine pipe closed while sending a request", retryable=False) from error
        try:
            answer = self._wait(ticket, timeout, control, request_id)
        finally:
            with self.lock:
                self.pending.pop(request_id, None)
        if "error" in answer:
            message = str(answer["error"])
            if message.startswith("CANCELLED"):
                raise ProtocolError("CANCELLED", "the engine confirmed that the request stopped", retryable=False)
            raise ProtocolError("ENGINE_ERROR", message[:2000], retryable=False)
        if not isinstance(answer.get("result"), dict):
            raise ProtocolError("OUTCOME_UNKNOWN", "the engine replied without a result", retryable=False)
        return answer["result"]

    def _wait(self, ticket: queue.Queue, timeout: float, control, request_id: int):
        deadline = time.monotonic() + timeout
        cancel_at = None
        while True:
            try:
                return ticket.get(timeout=0.05)
            except queue.Empty:
                pass
            now = time.monotonic()
            if self.closed.is_set() or now > deadline or (cancel_at is not None and now > cancel_at):
                self.close()
                code = "CANCELLED" if cancel_at is not None else "TIMEOUT"
                raise ProtocolError(code, "the engine did not confirm completion; its state is unknown",
                                    retryable=False)
            if control is not None and control.cancelled.is_set() and cancel_at is None:
                try:
                    self.send_control("cancel", requestId=request_id)
                except ProtocolError:
                    self.close()
                    raise ProtocolError("CLEANUP_INCOMPLETE", "could not ask the engine to cancel") from None
                cancel_at = now + 5

    def send_control(self, command: str, *, timeout: float = 5, **params):
        """A request whose reply is not interesting (cancel)."""
        ticket = queue.Queue(maxsize=1)
        with self.lock:
            if self.closed.is_set():
                raise EngineClosed("ENGINE_CLOSED", "the engine is closed")
            request_id = next(self.serial)
            self.pending[request_id] = ticket
            try:
                self.process.stdin.write(json.dumps({"id": request_id, "cmd": command, **params}).encode() + b"\n")
                self.process.stdin.flush()
            except OSError as error:
                self.pending.pop(request_id, None)
                raise ProtocolError("ENGINE_CLOSED", "the engine pipe closed", retryable=False) from error
        try:
            answer = self._wait(ticket, timeout, None, request_id)
        finally:
            with self.lock:
                self.pending.pop(request_id, None)
        return answer.get("result", {})

    def close(self) -> bool:
        """Stop the child and report whether it actually stopped."""
        self.closed.set()
        try:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
        except OSError:
            pass
        stopped = True
        try:
            self.process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                stopped = False
        self.reader.join(timeout=1)
        if self.process.stdout:
            self.process.stdout.close()
        if not self.log.closed:
            self.log.close()
        return stopped
