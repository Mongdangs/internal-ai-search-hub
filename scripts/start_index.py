from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


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
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/start_index.py <folder> [<folder> ...] [--rebuild]")

    root = Path(__file__).resolve().parents[1]
    rebuild = "--rebuild" in sys.argv[1:]
    target_folders = [arg for arg in sys.argv[1:] if arg != "--rebuild"]
    log_dir = root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "index.out.log"
    stderr_path = log_dir / "index.err.log"

    args = [sys.executable, "-B", "-m", "src.cli", "index", "--root", *target_folders]
    if rebuild:
        args.append("--rebuild")

    flags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS

    stdout = stdout_path.open("ab")
    stderr = stderr_path.open("ab")
    process = subprocess.Popen(
        args,
        cwd=root,
        env=clean_env(),
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        creationflags=flags,
        close_fds=True,
    )
    print(
        json.dumps(
            {
                "pid": process.pid,
                "folders": target_folders,
                "running": process.poll() is None,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
