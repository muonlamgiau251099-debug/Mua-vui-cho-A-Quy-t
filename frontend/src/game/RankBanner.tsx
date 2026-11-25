import { useCallback, useEffect, useRef, useState } from "react";
import type { SeatState } from "../api/guest";
import type { GameResult, LiveGame } from "./types";

type Rank = 1 | 2 | 4; // không có thông báo hạng Ba: tránh trùng với thông báo Bét lúc hết ván
type Item = { id: string; rank: Rank; name: string };

const AUTO_CLOSE_MS = 3000;
const MAX_QUEUE = 6;

const THEME: Record<Rank, { title: string; sub: string; crown: string; side: string }> = {
  1: { title: "CHAMPION!", sub: "NHẤT!", crown: "👑", side: "🏆" },
  2: { title: "AMAZING!", sub: "HẠNG NHÌ!", crown: "👑", side: "🥈" },
  4: { title: "HƠI ĐEN!", sub: "Bét mất rồi !", crown: "💧", side: "😥" },
};

const seatName = (seats: SeatState[], seat: number) => seats[seat]?.nickname ?? `Ghế ${seat + 1}`;

type Props = { game: LiveGame | null; result: GameResult | null; seats: SeatState[] };

/**
 * Thông báo thứ hạng ~3 giây cho mọi người (bấm "Xác nhận" để tắt sớm). Không hiện điểm: điểm cuối cùng
 * nằm ở bảng kết quả khi hết ván.
 * - Nhất / Nhì: lúc người đó hết bài giữa ván (sự kiện PLAYER_FINISHED).
 * - Bét: khi ván kết thúc bình thường (kể cả người cóng là Bét). Hạng Ba không có thông báo riêng.
 */
export function RankBanner({ game, result, seats }: Props) {
  const [queue, setQueue] = useState<Item[]>([]);
  const announced = useRef(new Set<string>());
  const firstGameSeen = useRef(false);
  const current = queue[0];

  const enqueue = useCallback((items: Item[]) => {
    if (items.length) setQueue((q) => [...q, ...items].slice(0, MAX_QUEUE));
  }, []);
  const dismiss = useCallback(() => setQueue((q) => q.slice(1)), []);

  // Người hết bài giữa ván. Bản chụp đầu tiên (vào bàn / kết nối lại) chỉ ghi nhận, không phát lại.
  useEffect(() => {
    if (!game) return;
    const items: Item[] = [];
    for (const e of game.events) {
      if (e.type !== "PLAYER_FINISHED") continue;
      const seat = e.seat as number;
      const rank = e.rank as number;
      const key = `${game.gameId}:${seat}`;
      if (announced.current.has(key)) continue;
      announced.current.add(key);
      if (firstGameSeen.current && (rank === 1 || rank === 2)) {
        items.push({ id: key, rank: rank as Rank, name: seatName(seats, seat) });
      }
    }
    firstGameSeen.current = true;
    enqueue(items);
  }, [game, seats, enqueue]);

  // Ván kết thúc bình thường: chỉ công bố Bét (kể cả người cóng).
  useEffect(() => {
    if (!result) return;
    const key = `ended:${result.gameId}`;
    if (announced.current.has(key)) return;
    announced.current.add(key);
    const r = result.result;
    if (r.endType !== "NORMAL") return;
    const items: Item[] = [];
    r.players.forEach((p) => {
      const base = { name: seatName(seats, p.seat) };
      if (p.status === "CONG" || (p.status === "FINISHED" && p.rank === r.players.length)) { // hạng cuối: 4 (ván 4 người) hoặc 3
        items.push({ ...base, id: `${result.gameId}:${p.seat}:4`, rank: 4 });
      }
    });
    enqueue(items.sort((a, b) => a.rank - b.rank));
  }, [result, seats, enqueue]);

  useEffect(() => {
    if (!current) return;
    const id = window.setTimeout(dismiss, AUTO_CLOSE_MS);
    return () => window.clearTimeout(id);
  }, [current, dismiss]);

  if (!current) return null;
  const theme = THEME[current.rank];
  return (
    <div className="rank-banner-wrap" role="status" aria-live="polite">
      <div className={`rank-banner rank-${current.rank}`} key={current.id}>
        {current.rank !== 4 && (
          <span className="rb-confetti" aria-hidden="true">
            {Array.from({ length: 12 }, (_, i) => (
              <i key={i} />
            ))}
          </span>
        )}
        <span className="rb-crown" aria-hidden="true">
          {theme.crown}
        </span>
        <div className="rb-title">{theme.title}</div>
        <div className="rb-sub">
          <span aria-hidden="true">{theme.side}</span> {theme.sub} <span aria-hidden="true">{theme.side}</span>
        </div>
        <div className="rb-pill">{current.name}</div>
        <button type="button" className="primary" onClick={dismiss}>
          Xác nhận
        </button>
      </div>
    </div>
  );
}
