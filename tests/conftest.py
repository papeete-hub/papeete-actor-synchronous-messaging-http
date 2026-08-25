"""Shared socket helpers for tests that spin up real `HttpMailbox`es on `127.0.0.1`.

Plain functions, not fixtures — each test file's own fixtures call these to pick a port and to
block until a `serve_forever()` thread is actually accepting connections, rather than racing it.
"""
from __future__ import annotations

import socket
import time


def free_port() -> int:
    """An unused localhost port, claimed and released — good enough between claim and bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_listening(port: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.02)
    raise TimeoutError(f"nothing listening on 127.0.0.1:{port} after {timeout}s")
