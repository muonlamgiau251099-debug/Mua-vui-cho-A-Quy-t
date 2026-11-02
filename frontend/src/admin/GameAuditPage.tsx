import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../api/client";

type Audit = {
  gameId: string;
  status: string;
  endType: string | null;
  cancelReason: string | null;
  ruleVersion: number;
  players: { seat: number; nickname: string | null }[];
  finalNet: number[];
  storedNet: number[] | null;
  verification: Record<string, boolean | number[]>;
  events: { seq: number; type: string; actorSeat: number | null; createdAt: string; stateHash: string | null }[];
};

const CHECK_LABEL: Record<string, string> = {
  deckCommitmentOk: "Bộ bài khớp mã kiểm chứng công bố lúc chia",
  rulesHashOk: "Luật của ván không bị sửa",
  replayMatchesStoredHash: "Chơi lại từ log ra đúng trạng thái đã lưu",
  resultMatchesReplay: "Điểm đã lưu khớp kết quả chơi lại",
  zeroSum: "Tổng điểm 4 người bằng 0",
};

// Đối soát tranh chấp (ID 155): Admin nhập mã ván, hệ thống kiểm tra lại toàn bộ bằng chứng.
export function GameAuditPage() {
  const [input, setInput] = useState("");
  const [gameId, setGameId] = useState<string | null>(null);
  const audit = useQuery({
    queryKey: ["admin", "audit", gameId],
    queryFn: () => api<Audit>(`/api/admin/games/${gameId}/audit`),
    enabled: !!gameId,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setGameId(input.trim() || null);
  };

  return (
    <section>
      <h1>Đối soát ván</h1>
      <form className="actions" onSubmit={submit}>
        <input aria-label="Mã ván" placeholder="Mã ván (gameId)" value={input} onChange={(e) => setInput(e.target.value)} size={40} />
        <button type="submit" className="primary">
          Kiểm tra
        </button>
      </form>
      {audit.isLoading && <p>Đang kiểm tra…</p>}
      {audit.error && <p role="alert">{errorMessage(audit.error)}</p>}
      {audit.data && (
        <>
          <p>
            Trạng thái: <strong>{audit.data.status}</strong>
            {audit.data.cancelReason && ` (${audit.data.cancelReason})`} · luật v{audit.data.ruleVersion} ·{" "}
            {audit.data.events.length} sự kiện
          </p>
          <ul className="issue-list">
            {Object.entries(CHECK_LABEL).map(([key, label]) => (
              <li key={key} className={audit.data.verification[key] ? "ok" : "error"}>
                {audit.data.verification[key] ? "✓" : "✗"} {label}
              </li>
            ))}
          </ul>
          <table className="data-table">
            <thead>
              <tr>
                <th>Người chơi</th>
                <th>Điểm chơi lại</th>
                <th>Điểm đã lưu</th>
              </tr>
            </thead>
            <tbody>
              {audit.data.players.map((p) => (
                <tr key={p.seat}>
                  <td>{p.nickname}</td>
                  <td>{audit.data.finalNet[p.seat]}</td>
                  <td>{audit.data.storedNet?.[p.seat] ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
