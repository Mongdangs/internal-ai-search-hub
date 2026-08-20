from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def next_port(start: int = 8501) -> int:
    port = start
    while port_is_open(port):
        port += 1
    return port


def clean_env() -> dict[str, str]:
    env = {}
    for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["PATH"] = os.environ.get("PATH") or os.environ.get("Path") or ""
    env["PYTHONUNBUFFERED"] = "1"
    return env


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    log_dir = root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    port = next_port(8501)

    stdout = (log_dir / "streamlit.out.log").open("ab")
    stderr = (log_dir / "streamlit.err.log").open("ab")
    flags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.port",
            str(port),
            "--server.address",
            "127.0.0.1",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=root,
        env=clean_env(),
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        creationflags=flags,
        close_fds=True,
    )

    for _ in range(30):
        if process.poll() is not None:
            break
        if port_is_open(port):
            break
        time.sleep(1)

    status = {
        "pid": process.pid,
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "running": process.poll() is None,
        "stdout": str(log_dir / "streamlit.out.log"),
        "stderr": str(log_dir / "streamlit.err.log"),
    }
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
