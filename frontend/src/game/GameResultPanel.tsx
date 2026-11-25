import type { SeatState } from "../api/guest";
import { cardsLabel, reasonLabel } from "./cards";
import type { GameResult } from "./types";

type Props = {
  result: GameResult;
  seats: SeatState[];
  yourSeat: number | null;
  onReady: () => void;
  onClose: () => void;
};

const END_LABEL: Record<string, string> = {
  NORMAL: "Ván kết thúc",
  INSTANT_WIN: "Tới trắng!",
  BLIND_THREE_SPADES: "Đút mù 3♠!",
  CANCELLED: "Ván bị hủy",
};
const RANK_LABEL = ["", "Nhất", "Nhì", "Ba", "Bét"];

export function GameResultPanel({ result, seats, yourSeat, onReady, onClose }: Props) {
  const r = result.result;
  const name = (seat: number) => (seat === yourSeat ? "Bạn" : (seats[seat]?.nickname ?? `Ghế ${seat + 1}`));
  const order = r.players.map((_, seat) => seat).sort((a, b) => (r.players[a]?.rank ?? 9) - (r.players[b]?.rank ?? 9));

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="result-title">
      <div className="dialog modal result">
        <div className="modal-head">
          <h2 id="result-title">{END_LABEL[r.endType ?? ""] ?? "Kết quả"}</h2>
        </div>
        <div className="modal-body">
        <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Hạng</th>
              <th>Người chơi</th>
              <th>Điểm ván</th>
              <th>Bài còn lại</th>
            </tr>
          </thead>
          <tbody>
            {order.map((seat) => {
              const p = r.players[seat]!;
              const net = r.net[seat] ?? 0;
              return (
                <tr key={seat}>
                  <td>
                    {/* D7: người cóng đồng bét — số hạng nội bộ chỉ để sắp thứ tự */}
                    {p.status === "CONG" ? "Bét (cóng)" : p.rank ? RANK_LABEL[p.rank] : "—"}
                    {p.status === "FORFEITED" && " (thoát)"}
                  </td>
                  <td>{name(seat)}</td>
                  <td className={net >= 0 ? "ok" : "error"}>{net > 0 ? `+${net}` : net}</td>
                  <td>{r.hands?.[seat]?.length ? cardsLabel(r.hands[seat]!) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>

        {r.transfers.length > 0 && (
          <>
            <h3>Chi tiết điểm</h3>
            <ul className="transfer-list">
              {r.transfers.map((t, i) => (
                <li key={i}>
                  {name(t.from)} trả {name(t.to)} <strong>{t.amount}</strong> — {reasonLabel(t.reason)}
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="muted small">
          Tổng điểm {r.players.length} người: {r.net.reduce((a, b) => a + b, 0)} · Luật v{result.rules.version}
          {result.deckReveal && ` · bộ bài đã công bố để kiểm chứng (salt ${result.deckReveal.salt.slice(0, 8)}…)`}
        </p>
        </div>
        <div className="dialog-actions">
          <button type="button" onClick={onClose}>
            Đóng
          </button>
          <button type="button" className="primary" onClick={onReady}>
            Sẵn sàng ván tiếp
          </button>
        </div>
      </div>
    </div>
  );
}
