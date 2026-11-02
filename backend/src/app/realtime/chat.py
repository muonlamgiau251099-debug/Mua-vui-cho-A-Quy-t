"""Chat nhanh bằng câu có sẵn trong phòng (message `chat.send` → broadcast `chat.message`).

- Không nhận chữ tự do: client chỉ gửi mã câu (phrase id) nằm trong danh sách cho phép.
- Giới hạn tần suất theo (phòng, guest) ở phía server; ngắt kết nối rồi vào lại cũng không reset được.
- Tin chat không lưu DB, không ảnh hưởng ván (không đi qua state machine hay sổ điểm).
"""

import time
from collections import OrderedDict
from collections.abc import Callable, Hashable

# Văn bản hiển thị nằm ở client (frontend/src/game/chat.ts); server chỉ biết mã.
CHAT_PHRASES: frozenset[str] = frozenset(
    {"duty", "hurry", "doomed", "redeal", "top1", "clan", "spare", "think"}
)
CHAT_COOLDOWN_SECONDS = 10.0
_MAX_TRACKED = 2000


class ChatCooldown:
    """Mỗi khóa chỉ được gửi 1 lần trong `cooldown` giây."""

    def __init__(
        self,
        cooldown: float = CHAT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        max_tracked: int = _MAX_TRACKED,
    ) -> None:
        self._cooldown = cooldown
        self._clock = clock
        self._max_tracked = max_tracked
        self._last: OrderedDict[Hashable, float] = OrderedDict()

    def check(self, key: Hashable) -> float:
        """Được gửi → ghi nhận và trả 0; chưa được → trả số giây còn phải chờ (không ghi nhận)."""
        now = self._clock()
        last = self._last.get(key)
        if last is not None and now - last < self._cooldown:
            return self._cooldown - (now - last)
        self._last[key] = now
        self._last.move_to_end(key)
        while len(self._last) > self._max_tracked:
            self._last.popitem(last=False)
        return 0.0
