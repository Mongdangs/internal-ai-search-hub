from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import quote, unquote
import secrets
import shutil
import socket
import threading
import time
from typing import Protocol

from src.config import AppConfig
from src.search.filters import path_startswith
from src.utils.file_utils import ensure_parent


DOWNLOAD_HOST = "127.0.0.1"
DOWNLOAD_PORT_START = 8765
DEFAULT_TOKEN_TTL_SECONDS = 15 * 60


class DownloadAuthorizer(Protocol):
    def can_download(self, file_path: Path, user_id: str | None = None) -> bool:
        ...


class AllowAllAclAuthorizer:
    def can_download(self, file_path: Path, user_id: str | None = None) -> bool:
        return True


class RootFolderDownloadAuthorizer:
    def __init__(self, root_folders: tuple[str, ...], acl_authorizer: DownloadAuthorizer | None = None) -> None:
        self.root_folders = tuple(str(root) for root in root_folders)
        self.acl_authorizer = acl_authorizer or AllowAllAclAuthorizer()

    def can_download(self, file_path: Path, user_id: str | None = None) -> bool:
        if not self._is_inside_allowed_root(file_path):
            return False
        return self.acl_authorizer.can_download(file_path, user_id)

    def _is_inside_allowed_root(self, file_path: Path) -> bool:
        try:
            resolved_path = file_path.resolve(strict=False)
        except OSError:
            resolved_path = file_path
        return any(path_startswith(str(resolved_path), root) or path_startswith(str(file_path), root) for root in self.root_folders)


@dataclass(frozen=True)
class DownloadToken:
    file_path: str
    expires_at: float
    user_id: str | None = None

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at


@dataclass
class DownloadAuditLogger:
    log_path: Path
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(
        self,
        event: str,
        file_path: str,
        status: str,
        reason: str = "",
        user_id: str | None = None,
        client_ip: str = "",
    ) -> None:
        ensure_parent(self.log_path)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "status": status,
            "reason": reason,
            "user_id": user_id or "",
            "client_ip": client_ip,
            "file_path": file_path,
        }
        with self.lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")


@dataclass
class DownloadRegistry:
    authorizer: DownloadAuthorizer
    audit_logger: DownloadAuditLogger
    token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS
    token_to_entry: dict[str, DownloadToken] = field(default_factory=dict)
    key_to_token: dict[str, str] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def register(self, file_path: str, user_id: str | None = None) -> str:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            self.audit_logger.record("register", str(path), "denied", "missing_file", user_id=user_id)
            raise FileNotFoundError(str(path))
        if not self.authorizer.can_download(path, user_id):
            self.audit_logger.record("register", str(path), "denied", "unauthorized_path_or_acl", user_id=user_id)
            raise PermissionError("download is not allowed for this file")

        self._cleanup_expired()
        cache_key = f"{path.resolve(strict=False)}:{user_id or ''}"
        expires_at = time.time() + self.token_ttl_seconds
        with self.lock:
            token = self.key_to_token.get(cache_key)
            if not token or token not in self.token_to_entry or self.token_to_entry[token].expired:
                token = secrets.token_urlsafe(24)
                self.key_to_token[cache_key] = token
            self.token_to_entry[token] = DownloadToken(str(path), expires_at, user_id)
        self.audit_logger.record("register", str(path), "allowed", user_id=user_id)
        return token

    def resolve(self, token: str, client_ip: str = "") -> DownloadToken | None:
        with self.lock:
            entry = self.token_to_entry.get(token)
            if entry is None:
                self.audit_logger.record("download", "", "denied", "invalid_token", client_ip=client_ip)
                return None
            if entry.expired:
                self.token_to_entry.pop(token, None)
                self.audit_logger.record(
                    "download",
                    entry.file_path,
                    "denied",
                    "expired_token",
                    user_id=entry.user_id,
                    client_ip=client_ip,
                )
                return None

        path = Path(entry.file_path)
        if not path.exists() or not path.is_file():
            self.audit_logger.record("download", entry.file_path, "denied", "missing_file", entry.user_id, client_ip)
            return None
        if not self.authorizer.can_download(path, entry.user_id):
            self.audit_logger.record("download", entry.file_path, "denied", "unauthorized_path_or_acl", entry.user_id, client_ip)
            return None
        self.audit_logger.record("download", entry.file_path, "allowed", user_id=entry.user_id, client_ip=client_ip)
        return entry

    def _cleanup_expired(self) -> None:
        with self.lock:
            expired = {token for token, entry in self.token_to_entry.items() if entry.expired}
            for token in expired:
                self.token_to_entry.pop(token, None)


class DownloadService:
    def __init__(
        self,
        config: AppConfig,
        authorizer: DownloadAuthorizer | None = None,
        token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
        host: str = DOWNLOAD_HOST,
        port_start: int = DOWNLOAD_PORT_START,
    ) -> None:
        self.config = config
        self.host = host
        self.port = _free_download_port(host, port_start)
        self.audit_logger = DownloadAuditLogger(config.data_dir / "logs" / "download_audit.log")
        self.registry = DownloadRegistry(
            authorizer or RootFolderDownloadAuthorizer(config.root_folders),
            self.audit_logger,
            token_ttl_seconds=token_ttl_seconds,
        )
        self.server = _build_server(self.host, self.port, self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, name="download-server", daemon=True)
        self.thread.start()

    def url_for(self, file_path: str, user_id: str | None = None) -> str:
        token = self.registry.register(file_path, user_id=user_id)
        return f"http://{self.host}:{self.port}/download/{token}"


def mime_type(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if suffix == ".ppt":
        return "application/vnd.ms-powerpoint"
    return mimetypes.guess_type(file_path)[0] or "application/octet-stream"


def _free_download_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("다운로드 서버 포트를 찾을 수 없습니다.")


def _build_server(host: str, port: int, registry: DownloadRegistry) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            prefix = "/download/"
            if not self.path.startswith(prefix):
                self.send_error(404)
                return
            token = unquote(self.path[len(prefix) :].split("?", 1)[0])
            client_ip = self.client_address[0] if self.client_address else ""
            entry = registry.resolve(token, client_ip=client_ip)
            if entry is None:
                self.send_error(403)
                return

            path = Path(entry.file_path)
            self.send_response(200)
            self.send_header("Content-Type", mime_type(str(path)))
            self.send_header("Content-Length", str(path.stat().st_size))
            ascii_name = path.name.encode("ascii", errors="ignore").decode("ascii") or "download"
            utf8_name = quote(path.name)
            self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}")
            self.end_headers()
            with path.open("rb") as f:
                shutil.copyfileobj(f, self.wfile, length=1024 * 1024)

        def log_message(self, format: str, *args) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)
