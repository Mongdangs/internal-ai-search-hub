from __future__ import annotations


class PasswordProtectedDocument(RuntimeError):
    """Raised when a document requires a password and must be skipped."""
