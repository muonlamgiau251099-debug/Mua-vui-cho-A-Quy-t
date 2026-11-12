import { Link } from "react-router-dom";
import type { SessionSummary } from "../api/guest";

type Props = { session: SessionSummary | null | undefined; yourSeat: number | null };

// Bảng điểm phiên hiện tại (ID 130): luôn hiện trong phòng chờ và bàn chơi.
export function SessionScoreboard({ session, yourSeat }: Props) {
  if (!session) return <p className="muted small">Phiên mới — điểm mọi người bắt đầu từ 0.</p>;
  const ranked = [...session.scores].sort((a, b) => b.total - a.total || a.seat - b.seat);
  return (
    <section className="scoreboard" aria-label="Điểm phiên">
      <div className="scoreboard-head">
        <strong>
          Phiên {session.sessionNo} · {session.gamesPlayed} ván
        </strong>
        <Link to={`/history/${session.sessionId}`}>Lịch sử</Link>
      </div>
      <ol>
        {ranked.map((s) => (
          <li key={s.seat} className={s.seat === yourSeat ? "you" : ""}>
            <span>
              {s.nickname ?? `Ghế ${s.seat + 1}`}
              {s.seat === yourSeat && " (bạn)"}
            </span>
            <strong className={s.total >= 0 ? "ok" : "error"}>{s.total > 0 ? `+${s.total}` : s.total}</strong>
          </li>
        ))}
      </ol>
    </section>
  );
}
