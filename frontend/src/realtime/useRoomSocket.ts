import { useCallback, useEffect, useRef, useState } from "react";
import type { RoomState } from "../api/guest";
import { errorLabel } from "../game/cards";
import { CHAT_SHOW_MS, chatText, cleanChatText, type ChatBubbles } from "../game/chat";
import { newRequestId } from "../lib/id";
import type { GameResult, LiveGame } from "../game/types";

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed";

type Envelope = { type: string; requestId?: string | null; sequence?: number | null; payload: Record<string, unknown> };

// Mã đóng kết nối mà client KHÔNG tự kết nối lại (docs/gd2/04 §2).
const FINAL_CLOSE: Record<number, string> = {
  4000: "Phòng đã đóng.",
  4001: "Bạn đã rời phòng.",
  4401: "Phiên chơi không hợp lệ, hãy nhập tên lại.",
  // 4408 (hết thời gian xác thực) không nằm ở đây: client tự kết nối lại.
  4403: "Bạn không còn ghế trong phòng này.",
  4409: "Bạn vừa mở phòng này ở tab hoặc thiết bị khác.",
  4429: "Gửi thao tác quá nhanh, kết nối bị ngắt.",
};

export function closeReason(code: number): string | null {
  return FINAL_CLOSE[code] ?? null;
}

/** 0.5s, 1s, 2s, 4s, rồi tối đa 8s giữa các lần kết nối lại. */
export function reconnectDelay(attempt: number): number {
  return Math.min(8000, 500 * 2 ** Math.max(0, attempt - 1));
}

/** Chỉ nhận trạng thái mới hơn (version tăng dần) — bỏ qua message đến trễ. */
export function newerState(prev: RoomState | null, next: RoomState): RoomState {
  return prev && prev.roomId === next.roomId && prev.version > next.version ? prev : next;
}

/** Trạng thái ván mới hơn theo sequence; ván khác (gameId mới) luôn được nhận. */
export function newerGame(prev: LiveGame | null, next: LiveGame): LiveGame {
  return prev && prev.gameId === next.gameId && prev.sequence > next.sequence ? prev : next;
}

function socketUrl(roomId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/rooms/${roomId}`;
}

export function useRoomSocket(roomId: string | null, token: string | null) {
  const [room, setRoom] = useState<RoomState | null>(null);
  const [game, setGame] = useState<LiveGame | null>(null);
  const [result, setResult] = useState<GameResult | null>(null);
  const [chats, setChats] = useState<ChatBubbles>({});
  const [status, setStatus] = useState<SocketStatus>("connecting");
  const [finalMessage, setFinalMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  // Độ lệch giữa đồng hồ server và máy người chơi (giây) — đồng hồ lượt đếm theo giờ server.
  const [clockOffset, setClockOffset] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const gameRef = useRef<LiveGame | null>(null);
  gameRef.current = game;

  useEffect(() => {
    if (!roomId || !token) return;
    let stopped = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let chatKey = 0;
    const chatTimers = new Set<ReturnType<typeof setTimeout>>();

    const handle = (msg: Envelope) => {
      const p = msg.payload;
      switch (msg.type) {
        case "ack":
          if (p.type === "auth") {
            attempt = 0;
            setStatus("open");
            if (typeof p.serverTime === "number") setClockOffset(p.serverTime - Date.now() / 1000);
          }
          setLastError(null);
          break;
        case "room.state":
          setRoom((prev) => newerState(prev, p as unknown as RoomState));
          break;
        case "room.allReady":
          setNotice("Đủ 4 người sẵn sàng — đang chia bài!");
          break;
        case "game.started":
        case "game.update":
        case "game.state": {
          const next = { ...(p as unknown as Omit<LiveGame, "sequence">), sequence: msg.sequence ?? 0 };
          if (msg.type === "game.started") {
            setResult(null);
            setNotice(null); // thông báo "đang chia bài" đã xong việc
          }
          setGame((prev) => newerGame(prev, next as LiveGame));
          break;
        }
        case "game.ended":
          setResult(p as unknown as GameResult);
          setGame(null);
          break;
        case "game.cancelled":
          setGame(null);
          setNotice("Ván đã bị hủy, điểm của ván không được tính.");
          break;
        case "session.restarted":
          setNotice("Chủ phòng đã bắt đầu phiên mới — điểm mọi người về 0 từ ván tiếp theo.");
          break;
        case "rules.updated":
          setNotice(`Luật v${String(p.version)} sẽ áp dụng từ ván tiếp theo.`);
          break;
        case "chat.message": {
          const seat = p.seat;
          if (typeof seat !== "number" || !Number.isInteger(seat) || seat < 0 || seat > 3) break;
          // Câu có sẵn (mã → chữ) hoặc chữ tự do. Chữ tự do luôn được làm sạch lại và chỉ hiển thị như văn bản thuần.
          const text =
            typeof p.phrase === "string" ? chatText(p.phrase) : typeof p.text === "string" ? cleanChatText(p.text) : null;
          if (!text) break;
          const key = ++chatKey;
          setChats((prev) => ({ ...prev, [seat]: { text, key } }));
          chatTimers.add(
            setTimeout(
              () =>
                setChats((prev) => {
                  if (prev[seat]?.key !== key) return prev; // đã có câu mới hơn của người này
                  const next = { ...prev };
                  delete next[seat];
                  return next;
                }),
              CHAT_SHOW_MS,
            ),
          );
          break;
        }
        case "daily.resetPending":
          setNotice("Đã sang ngày mới (giờ Nhật). Chơi hết ván này rồi phòng sẽ được xóa.");
          break;
        case "room.closed":
          setFinalMessage(p.reason === "DAILY_RESET" ? "Đã kết thúc ván và xóa dữ liệu ngày cũ (00:00 giờ Nhật). Hãy về sảnh để vào chơi lại." : p.reason === "OWNER_CLOSED" ? "Chủ phòng đã đóng phòng." : "Phòng đã đóng.");
          break;
        case "error":
          setLastError(errorLabel(String(p.code), typeof p.message === "string" ? p.message : "Có lỗi xảy ra"));
          break;
      }
    };

    const connect = () => {
      const ws = new WebSocket(socketUrl(roomId));
      wsRef.current = ws;
      setStatus(attempt === 0 ? "connecting" : "reconnecting");
      ws.onopen = () => ws.send(JSON.stringify({ type: "auth", requestId: newRequestId(), payload: { token } }));
      ws.onmessage = (event) => {
        try {
          handle(JSON.parse(String(event.data)) as Envelope);
        } catch {
          /* bỏ qua gói tin hỏng */
        }
      };
      ws.onclose = (event) => {
        if (stopped) return;
        const reason = closeReason(event.code);
        if (reason) {
          setStatus("closed");
          setFinalMessage((prev) => prev ?? reason);
          return;
        }
        attempt += 1;
        setStatus("reconnecting");
        timer = setTimeout(connect, reconnectDelay(attempt));
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      chatTimers.forEach(clearTimeout);
      wsRef.current?.close(1000);
    };
  }, [roomId, token]);

  const send = useCallback(
    (type: string, payload: Record<string, unknown> = {}) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      // sequence = trạng thái ván client đang thấy (baseSeq); server từ chối nếu đã cũ (G9).
      const sequence = gameRef.current?.sequence ?? 0;
      ws.send(JSON.stringify({ type, requestId: newRequestId(), roomId, sequence, payload }));
      return true;
    },
    [roomId],
  );

  return {
    room,
    game,
    result,
    chats,
    clockOffset,
    status,
    finalMessage,
    notice,
    lastError,
    send,
    clearNotice: () => setNotice(null),
    clearResult: () => setResult(null),
  };
}
