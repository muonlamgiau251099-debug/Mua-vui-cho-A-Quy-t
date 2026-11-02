import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { historyApi } from "../api/guest";
import { reasonLabel } from "../game/cards";

const END_LABEL: Record<string, string> = {
  NORMAL: "Bình thường",
  INSTANT_WIN: "Tới trắng",
  BLIND_THREE_SPADES: "Đút mù 3♠",
  CANCELLED: "Bị hủy",
};
const CANCEL_LABEL: Record<string, string> = {
  ADMIN: "Admin hủy",
  ROOM_CLOSED: "đóng phòng",
  SERVER_RESTART: "server khởi động lại",
  ALL_LEFT: "mọi người rời",
};

const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

// Lịch sử phiên (ID 130, 131, 150): tổng kết + biến động điểm từng ván + chi tiết từng khoản.
export function HistoryPage() {
  const { sessionId = "" } = useParams();
  const detail = useQuery({ queryKey: ["session", sessionId], queryFn: () => historyApi.session(sessionId) });
  const [open, setOpen] = useState<string | null>(null);

  if (detail.isLoading) return <main className="app">Đang tải…</main>;
  if (detail.error)
    return (
      <main className="app narrow">
        <p role="alert">{errorMessage(detail.error)}</p>
        <Link to="/lobby">Về sảnh</Link>
      </main>
    );
  const d = detail.data!;
  const name = (seat: number) => d.players[seat]?.nickname ?? `Ghế ${seat + 1}`;

  return (
    <main className="app wide">
      <p>
        <Link to={`/r/${d.roomCode}`}>← Về phòng {d.roomCode}</Link>
      </p>
      <h1>
        Phiên {d.sessionNo} · phòng {d.roomCode}
      </h1>
      <p className="muted">
        Bắt đầu {new Date(d.startedAt).toLocaleString("vi-VN")}
        {d.endedAt && ` · kết thúc ${new Date(d.endedAt).toLocaleString("vi-VN")}`}
        {d.endReason === "RESTARTED" && " (chủ phòng khởi động lại phiên)"}
        {d.endReason === "ROSTER_CHANGED" && " (đổi người chơi)"}
      </p>

      <h2>Tổng kết</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Hạng</th>
            <th>Người chơi</th>
            <th>Tổng điểm</th>
            <th>Số ván</th>
          </tr>
        </thead>
        <tbody>
          {d.standings.map((s) => (
            <tr key={s.seat}>
              <td>{s.place}</td>
              <td>{s.nickname}</td>
              <td className={s.total >= 0 ? "ok" : "error"}>{signed(s.total)}</td>
              <td>{s.gamesCounted}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Từng ván</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Ván</th>
              <th>Kết thúc</th>
              {d.players.map((p) => (
                <th key={p.seat}>{p.nickname}</th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {d.games.map((g) => (
              <Fragment key={g.gameId}>
                <tr>
                  <td>
                    #{g.gameNo} <span className="muted small">luật v{g.ruleVersion}</span>
                  </td>
                  <td>
                    {g.status === "CANCELLED"
                      ? `Bị hủy (${CANCEL_LABEL[g.cancelReason ?? ""] ?? g.cancelReason}) — không tính điểm`
                      : g.status === "IN_PROGRESS"
                        ? "Đang chơi"
                        : (END_LABEL[g.endType ?? ""] ?? g.status)}
                  </td>
                  {d.players.map((p) => (
                    <td key={p.seat}>
                      {g.net ? (
                        <>
                          <span className={g.net[p.seat]! >= 0 ? "ok" : "error"}>{signed(g.net[p.seat]!)}</span>
                          <span className="muted small"> ({signed(g.cumulative![p.seat]!)})</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  ))}
                  <td className="actions">
                    {g.status !== "IN_PROGRESS" && <Link to={`/replay/${g.gameId}`}>Xem lại</Link>}
                    {g.transfers.length > 0 && (
                      <button type="button" onClick={() => setOpen(open === g.gameId ? null : g.gameId)}>
                        {open === g.gameId ? "Ẩn" : "Chi tiết"}
                      </button>
                    )}
                  </td>
                </tr>
                {open === g.gameId && (
                  <tr>
                    <td colSpan={d.players.length + 3}>
                      <ul className="transfer-list">
                        {g.transfers.map((t, i) => (
                          <li key={i}>
                            {name(t.from)} trả {name(t.to)} <strong>{t.amount}</strong> — {reasonLabel(t.reason)}
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">Số trong ngoặc là điểm cộng dồn sau ván đó. Tổng điểm 4 người mỗi ván luôn bằng 0.</p>
    </main>
  );
}
