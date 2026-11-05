"""Chat trong phòng: câu có sẵn hoặc chữ tự do ngắn (`chat.send` → broadcast `chat.message`).

- Câu có sẵn: client chỉ gửi mã (phrase id) nằm trong danh sách cho phép.
- Chữ tự do: server tự làm sạch (bỏ ký tự điều khiển, gộp khoảng trắng) và giới hạn độ dài; không tin client.
  Chat không kiểm duyệt từ ngữ; client hiển thị như văn bản thuần (không HTML).
- Giới hạn tần suất theo (phòng, guest) ở phía server; ngắt kết nối rồi vào lại cũng không reset được.
- Tin chat không lưu DB, không ghi log nội dung, không ảnh hưởng ván (không đi qua state machine hay sổ điểm).
"""

import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable, Hashable

# Văn bản hiển thị của câu có sẵn nằm ở client (frontend/src/game/chat.ts); server chỉ biết mã.
CHAT_PHRASES: frozenset[str] = frozenset(
    {
        "duty",
        "hurry",
        "doomed",
        "redeal",
        "top1",
        "clan",
        "spare",
        "think",
        "spade3",
        "mistake",
        "undo",
    }
)
CHAT_MAX_LENGTH = 60  # ký tự (code point) của chữ tự do
CHAT_COOLDOWN_SECONDS = 4.0
_MAX_TRACKED = 2000
_ZWJ = chr(0x200D)  # zero-width joiner: giữ lại để emoji ghép không bị vỡ


def normalize_chat_text(raw: object) -> str | None:
    """Làm sạch chữ tự do; trả None nếu không phải chuỗi, rỗng sau khi làm sạch, hoặc quá dài."""
    if not isinstance(raw, str):
        return None
    # Ký tự điều khiển / định dạng / riêng tư (nhóm C*, gồm xuống dòng, đảo chiều chữ…) → khoảng trắng.
    spaced = "".join(" " if unicodedata.category(ch).startswith("C") and ch != _ZWJ else ch for ch in raw)
    text = " ".join(spaced.split())
    if not text or len(text) > CHAT_MAX_LENGTH:
        return None
    return text


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
