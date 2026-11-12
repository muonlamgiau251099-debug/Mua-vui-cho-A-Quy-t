"""Băm mật khẩu (argon2id), token ngẫu nhiên và rate limit trong bộ nhớ (1 process — ADR-003)."""

import hashlib
import secrets
import time
from collections import deque
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2id với tham số mặc định của thư viện
# Hash giả để thời gian xử lý "không có user" giống "sai mật khẩu" (tránh dò username).
_DUMMY_HASH = _hasher.hash("tlmn-dummy-password")

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SlidingWindowLimiter:
    """Giới hạn số lần trong một cửa sổ thời gian theo khóa (vd IP)."""

    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
