import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { historyApi } from "../api/guest";
import { cardLabel, comboLabel, isRed } from "../game/cards";
import { describeEvent } from "../game/GameTable";

// Xem lại ván từng bước (ID 154). Chỉ mở được sau khi ván kết thúc nên hiện bài của mọi người chơi.
export function ReplayPage() {
  const { gameId = "" } = useParams();
  const replay = useQuery({ queryKey: ["replay", gameId], queryFn: () => historyApi.replay(gameId) });
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const total = replay.data?.steps.length ?? 0;

  useEffect(() => {
    if (!playing) return;
    if (step >= total) {
      setPlaying(false);
      return;
    }
    const id = setTimeout(() => setStep((s) => s + 1), 900);
    return () => clearTimeout(id);
  }, [playing, step, total]);

  if (replay.isLoading) return <main className="app">Đang tải…</main>;
  if (replay.error)
    return (
      <main className="app narrow">
        <p role="alert">{errorMessage(replay.error)}</p>
        <Link to="/lobby">Về sảnh</Link>
      </main>
    );
  const r = replay.data!;
  const current = step === 0 ? null : r.steps[step - 1]!;
  const view = current ? current.view : r.initial;
  const name = (seat: number) => r.players[seat]?.nickname ?? `Ghế ${seat + 1}`;
  const lines = (current?.events ?? []).map((e) => describeEvent(e, name)).filter(Boolean);

  return (
    <main className="app wide">
      <p>
        <Link to={`/history/${r.sessionId}`}>← Lịch sử phiên</Link>
      </p>
      <h1>
        Xem lại ván #{r.gameNo} · phòng {r.roomCode}
      </h1>
      <p className="muted small">
        Luật v{r.ruleVersion} ·{" "}
        {r.verified ? "✓ Log khớp với kết quả đã lưu" : "⚠ Log không khớp — hãy báo Admin"} · bộ bài kiểm chứng{" "}
        {r.deckCommitment.slice(0, 10)}…
      </p>

      <div className="replay-controls actions">
        <button type="button" onClick={() => setStep(0)} disabled={step === 0}>
          ⏮ Đầu ván
        </button>
        <button type="button" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
          ◀ Lùi
        </button>
        <button type="button" className="primary" onClick={() => setPlaying((p) => !p)} disabled={step >= total && !playing}>
          {playing ? "⏸ Dừng" : "▶ Tự chạy"}
        </button>
        <button type="button" onClick={() => setStep((s) => Math.min(total, s + 1))} disabled={step >= total}>
          Tới ▶
        </button>
        <button type="button" onClick={() => setStep(total)} disabled={step >= total}>
          Cuối ván ⏭
        </button>
        <input
          type="range"
          min={0}
          max={total}
          value={step}
          aria-label="Bước"
          onChange={(e) => setStep(Number(e.target.value))}
        />
        <span className="muted">
          Bước {step}/{total}
        </span>
      </div>

      <div className="replay-event" aria-live="polite">
        {step === 0 ? "Vừa chia bài." : lines.length ? lines.join(" · ") : current?.kind}
      </div>

      <div className="trick">
        {view.trick.top ? (
          <>
            <div className="trick-cards">
              {view.trick.top.map((c) => (
                <span key={c} className={`card${isRed(c) ? " red" : ""}`}>
                  {cardLabel(c)}
                </span>
              ))}
            </div>
            <div className="muted small">
              {comboLabel(view.trick.topCombo)} của {name(view.trick.topSeat ?? 0)}
            </div>
          </>
        ) : (
          <div className="muted">{view.phase === "PLAYING" ? `${name(view.trick.leader)} mở vòng` : "Ván kết thúc"}</div>
        )}
      </div>

      <div className="replay-hands">
        {view.hands.map((hand, seat) => (
          <section key={seat} className={`replay-hand${view.current === seat ? " turn" : ""}`}>
            <strong>
              {name(seat)} {view.players[seat]?.rank ? `· hạng ${view.players[seat]!.rank}` : ""}
              {view.players[seat]?.status === "CONG" && " · cóng"}
            </strong>
            <div className="my-hand">
              {hand.map((c) => (
                <span key={c} className={`card${isRed(c) ? " red" : ""}`}>
                  {cardLabel(c)}
                </span>
              ))}
              {hand.length === 0 && <span className="muted">Hết bài</span>}
            </div>
          </section>
        ))}
      </div>

      {view.phase !== "PLAYING" && (
        <p>
          Điểm ván:{" "}
          {view.net.map((n, seat) => `${name(seat)} ${n > 0 ? `+${n}` : n}`).join(" · ")}
        </p>
      )}
    </main>
  );
}
