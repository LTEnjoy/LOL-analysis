#!/usr/bin/env python3
"""Start lcu_server.py in the background if it is not already running.

Used by the `lolsync://start` protocol handler so the website button can
bring the local bridge up without a visible console.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SERVER = BASE / "scripts" / "lcu_server.py"
DEFAULT_PORT = 8765


def bridge_healthy(port, timeout=0.8):
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=timeout,
        ) as response:
            return response.status == 200
    except Exception:
        return False


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main():
    port = int(os.environ.get("LCU_SYNC_PORT", DEFAULT_PORT))
    if bridge_healthy(port):
        return 0
    if port_in_use(port):
        # Some other process owns the port; report failure instead of spawning.
        return 1

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    executable = pythonw if pythonw.is_file() else Path(sys.executable)
    flags = 0
    if os.name == "nt":
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    subprocess.Popen(
        [str(executable), str(SERVER), "--port", str(port)],
        cwd=str(BASE),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )

    for _ in range(40):
        if bridge_healthy(port):
            return 0
        time.sleep(0.25)
    return 1


if __name__ == "__main__":
    sys.exit(main())
