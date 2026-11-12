import { useEffect, useState, type ReactNode } from "react";
import type { RoomState, SeatState } from "../api/guest";
import { Modal } from "../game/Modal";
import { avatarFor } from "../lib/avatars";
import { COMPACT_QUERY, useMediaQuery } from "../lib/useMediaQuery";
import { RulesView } from "../pages/RulesView";

type Props = {
  room: RoomState;
  yourSeat: number | null;
  canAct: boolean;
  inviteUrl: string;
  info?: ReactNode; // màn hình nhỏ: nội dung popup "Thông tin" (điểm phiên)
  onReady: (ready: boolean) => void;
  onLeave: () => void;
  onClose: () => void;
  onKick?: (seat: SeatState) => void;
  onRestartSession?: () => void;
  onChangePlayerCount?: (count: 3 | 4) => void; // chỉ chủ phòng: đổi phòng giữa 3 và 4 người
};

/** navigator.clipboard chỉ có trên HTTPS/localhost; mở qua IP LAN (HTTP) thì dùng cách cũ execCommand. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* thử cách dự phòng bên dưới */
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

function secondsLeft(iso: string | null, now: number): number | null {
  return iso ? Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000)) : null;
}

const SEAT_POS = ["me", "left", "top", "right"] as const;
const SEAT_POS_3 = ["me", "left", "right"] as const; // phòng 3 người: không có ghế đối diện

type SeatCardProps = {
  seat: SeatState;
  pos: (typeof SEAT_POS)[number];
  isOwner: boolean;
  isYou: boolean;
  now: number;
  onKick?: () => void; // chỉ truyền khi bạn là chủ phòng và ghế này là người khác
};

function SeatCard({ seat, pos, isOwner, isYou, now, onKick }: SeatCardProps) {
  const hold = secondsLeft(seat.holdUntil, now);
  const ready = seat.occupied && seat.connected && seat.ready;
  return (
    <li className={`seat-card pos-${pos}${isYou ? " you" : ""}${seat.occupied ? "" : " empty"}${ready ? " is-ready" : ""}`}>
      <span className="avatar-wrap">
        <span className="avatar" aria-hidden="true">
          {seat.occupied ? <img src={avatarFor(seat.seatNo)} alt="" /> : "+"}
        </span>
        {seat.occupied && onKick && (
          <button
            type="button"
            className="kick-btn"
            aria-label={`Mời ${seat.nickname ?? "người chơi"} ra khỏi phòng`}
            title="Mời ra khỏi phòng"
            onClick={onKick}
          >
            {/* Vẽ bằng SVG để dấu × nằm đúng tâm (ký tự "×" lệch theo baseline của font) */}
            <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true">
              <path d="M2 2 8 8M8 2 2 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        )}
      </span>
      <div className="seat-title">
        Ghế {seat.seatNo + 1}
        {isOwner && <span title="Chủ phòng"> 👑</span>}
      </div>
      {seat.occupied ? (
        <>
          <div className="seat-name">
            {seat.nickname}
            {isYou && " (bạn)"}
          </div>
          <div className="seat-status">
            {!seat.connected ? (
              <span className="warn">⟳ Mất kết nối{hold !== null ? ` · giữ ghế ${hold}s` : ""}</span>
            ) : seat.ready ? (
              <span className="ok">✓ Sẵn sàng</span>
            ) : (
              <span className="muted">Chưa sẵn sàng</span>
            )}
          </div>
        </>
      ) : (
        <div className="seat-name muted">Ghế trống</div>
      )}
    </li>
  );
}

export function WaitingRoom({
  room,
  yourSeat,
  canAct,
  inviteUrl,
  info,
  onReady,
  onLeave,
  onClose,
  onKick,
  onRestartSession,
  onChangePlayerCount,
}: Props) {
  const compact = useMediaQuery(COMPACT_QUERY);
  const [infoOpen, setInfoOpen] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const me = yourSeat === null ? undefined : room.seats[yourSeat];
  const occupied = room.seats.filter((s) => s.occupied).length;
  const readyCount = room.seats.filter((s) => s.occupied && s.ready).length;
  const isOwner = yourSeat !== null && yourSeat === room.ownerSeat;

  const copy = async () => {
    const ok = await copyText(inviteUrl);
    setCopied(ok);
    if (ok) setTimeout(() => setCopied(false), 2000);
    else window.prompt("Sao chép link mời này:", inviteUrl); // trình duyệt chặn sao chép tự động
  };

  return (
    <section className={`waiting-room${compact ? " compact" : ""}`}>
      <h1 className="sr-only">Phòng {room.code}</h1>
      <div className="waiting-table">
        <div className="room-info">
          <span className="room-count">
            {occupied}/{room.seats.length} người · {readyCount} sẵn sàng
          </span>
          {room.rules && (
            <button type="button" className="link-btn rules-link" onClick={() => setRulesOpen(true)}>
              Luật v{room.rules.version}
            </button>
          )}
        </div>

        <button type="button" className="table-btn leave-btn" onClick={onLeave}>
          Rời phòng
        </button>

        <ol className="seat-ring" aria-label="Các ghế trong phòng">
          {(room.seats.length === 3 ? SEAT_POS_3 : SEAT_POS).map((pos, offset) => {
            // Bạn luôn ngồi phía dưới; ghế kế tiếp bên trái, (4 người: đối diện ở trên), ghế trước bên phải.
            const seat = room.seats[((yourSeat ?? 0) + offset) % room.seats.length]!;
            return (
              <SeatCard
                key={seat.seatNo}
                seat={seat}
                pos={pos}
                isOwner={seat.seatNo === room.ownerSeat}
                isYou={seat.seatNo === yourSeat}
                now={now}
                onKick={
                  isOwner && onKick && seat.occupied && seat.seatNo !== yourSeat ? () => onKick(seat) : undefined
                }
              />
            );
          })}
        </ol>

        <div className="table-center">
          <button
            type="button"
            className={`ready-btn${me?.ready ? " is-ready" : ""}`}
            disabled={!canAct || !me}
            onClick={() => onReady(!me?.ready)}
          >
            {me?.ready ? "Hủy sẵn sàng" : "Sẵn sàng"}
          </button>
          <div className="room-code-row">
            <span className="small">Mã phòng</span>
            <span className="table-code">{room.code}</span>
            <button
              type="button"
              className="copy-btn"
              aria-label="Sao chép link mời"
              title="Sao chép link mời"
              onClick={copy}
            >
              {copied ? "✓" : "⧉"}
            </button>
          </div>
          {copied && (
            <span className="copied-note small" role="status">
              Đã sao chép link mời
            </span>
          )}
          {occupied < room.seats.length && (
            <p className="hint">Cần đủ {room.seats.length} người — gửi mã hoặc link mời cho bạn bè.</p>
          )}
          {isOwner && onChangePlayerCount && (
            <div className="player-count" role="group" aria-label="Số người chơi">
              <span className="small">Số người</span>
              {([3, 4] as const).map((n) => (
                <button
                  key={n}
                  type="button"
                  aria-pressed={room.seats.length === n}
                  disabled={room.seats.length === n}
                  onClick={() => onChangePlayerCount(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="room-corner">
          {compact && info && (
            <button type="button" className="table-btn" onClick={() => setInfoOpen(true)}>
              ⓘ Thông tin
            </button>
          )}
          {isOwner && room.session && onRestartSession && (
            <button type="button" className="table-btn" onClick={onRestartSession}>
              Bắt đầu phiên mới
            </button>
          )}
        </div>

        {isOwner && (
          <button type="button" className="table-btn close-btn danger" onClick={onClose}>
            Đóng phòng
          </button>
        )}
      </div>

      {infoOpen && (
        <Modal title="Thông tin" onClose={() => setInfoOpen(false)}>
          {info}
        </Modal>
      )}
      {rulesOpen && (
        <Modal title="Luật đang áp dụng" wide onClose={() => setRulesOpen(false)}>
          <RulesView />
        </Modal>
      )}
    </section>
  );
}
