import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { SeatState } from "../api/guest";
import { useMediaQuery } from "../lib/useMediaQuery";
import { cardLabel, cardsLabel, comboLabel, isRed, rankOf, sortHand, suitOf, type SortMode } from "./cards";
import { CHAT_COOLDOWN_MS, CHAT_PHRASES, chatText, type ChatBubbles } from "./chat";
import type { GameEvent, LiveGame, PlayerView } from "./types";

type Props = {
  game: LiveGame;
  seats: SeatState[];
  canAct: boolean;
  error: string | null;
  clockOffset?: number; // giây: giờ server − giờ máy này
  onPlay: (cards: number[]) => void;
  onPass: () => void;
  chats?: ChatBubbles; // bong bóng chat đang hiện, theo số ghế
  onChat?: (phraseId: string) => boolean | void; // trả false nếu chưa gửi được (mất kết nối)
};

const STATUS_LABEL: Record<PlayerView["status"], string> = {
  ACTIVE: "",
  FINISHED: "Đã hết bài",
  CONG: "Cóng",
  FORFEITED: "Đã thoát",
};
const RANK_LABEL = ["", "Nhất", "Nhì", "Ba", "Bét"];

export function describeEvent(event: GameEvent, name: (seat: number) => string): string | null {
  const who = typeof event.seat === "number" ? name(event.seat) : "";
  switch (event.type) {
    case "PLAYED": {
      const cards = cardsLabel(event.cards as number[]);
      const verb = event.interrupt ? "chặt ngoài lượt" : event.chop ? "chặt" : "đánh";
      return `${who} ${verb} ${cards}${event.auto ? " (hết giờ, tự đánh)" : ""}`;
    }
    case "PASSED":
      return `${who} bỏ lượt${event.auto ? " (hết giờ)" : ""}`;
    case "TRICK_CLOSED":
      return `${name(event.nextLeader as number)} mở vòng mới`;
    case "PLAYER_FINISHED":
      return `${who} hết bài — về ${RANK_LABEL[event.rank as number]?.toLowerCase()}`;
    case "CONG":
      return `${(event.seats as number[]).map(name).join(", ")} bị cóng`;
    case "PLAYER_FORFEITED":
      return `${who} thoát ván`;
    default:
      return null;
  }
}

function useSecondsLeft(deadline: number | null, offset: number): number | null {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 250);
    return () => clearInterval(id);
  }, []);
  return deadline === null ? null : Math.max(0, Math.ceil(deadline - (now + offset)));
}

const SUIT_NAME = ["bích", "chuồn", "rô", "cơ"]; // ♠ ♣ ♦ ♥ (theo mã lá bài của engine)
const TWO_RANK = 12;
const TWO_GROUP: Record<string, string> = { PAIR: "Đôi 2", TRIPLE: "3 con 2" };

/**
 * Tên hiển thị khi đánh bài đặc biệt: heo (2 đơn / đôi 2 / 3 con 2), tứ quý, 3-4… đôi thông,
 * 3 con cùng số ("Hút thuốc").
 * Trả về null nếu không phải trường hợp đặc biệt.
 */
export function specialPlayLabel(combo: string | null, cards: number[]): string | null {
  if (combo === "FOUR_KIND") return "Tứ quý";
  if (combo === "PAIR_SEQ") return `${Math.floor(cards.length / 2)} đôi thông`;
  if (cards.length > 0 && cards.every((c) => rankOf(c) === TWO_RANK)) {
    if (combo === "SINGLE") return `2 ${SUIT_NAME[suitOf(cards[0]!)]}`;
    return (combo && TWO_GROUP[combo]) || null;
  }
  if (combo === "TRIPLE") return "Hút thuốc"; // 3 con cùng số (3 con ba, 3 con 5…); 3 con 2 đã xử lý ở trên
  return null;
}

/** Chữ cong vòng cung, to và tròn: "Ba đôi thông nè !!!". */
function PlayBurst({ text, who }: { text: string; who: string }) {
  const size = Math.min(56, Math.floor(450 / (text.length * 0.62)));
  return (
    <div className="play-burst" role="status">
      <span className="sr-only">
        {who}: {text}
      </span>
      <div className="burst-inner" aria-hidden="true">
        <span className="burst-who">{who}</span>
        <svg viewBox="0 0 480 140">
          <defs>
            <linearGradient id="burst-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#fff3a6" />
              <stop offset="100%" stopColor="#ffb938" />
            </linearGradient>
          </defs>
          <path id="burst-arc" d="M 20 120 Q 240 -30 460 120" fill="none" />
          <text fontSize={size} fill="url(#burst-fill)">
            <textPath href="#burst-arc" startOffset="50%" textAnchor="middle">
              {text}
            </textPath>
          </text>
        </svg>
      </div>
    </div>
  );
}

type CardFaceProps = { card: number; selected?: boolean; index?: number; onClick?: () => void };

function CardFace({ card, selected, index, onClick }: CardFaceProps) {
  const className = `card${isRed(card) ? " red" : ""}${selected ? " selected" : ""}`;
  return onClick ? (
    <button type="button" className={className} aria-pressed={selected} data-card-idx={index} onClick={onClick}>
      {cardLabel(card)}
    </button>
  ) : (
    <span className={className}>{cardLabel(card)}</span>
  );
}

/** Bong bóng chat kiểu pixel, hiện ra từ avatar người gửi. */
function SpeechBubble({ phrase, tail }: { phrase: string; tail: "left" | "right" | "side" }) {
  // left/right: bong bóng nằm trên avatar, đuôi chỉ xuống avatar; side: nằm bên phải avatar, đuôi chỉ sang trái.
  const text = chatText(phrase);
  return text ? (
    <div className={`chat-bubble tail-${tail}`} role="status">
      {text}
    </div>
  ) : null;
}

/** Nút chat: mở danh sách câu có sẵn, khóa 10 giây sau mỗi lần gửi. */
function ChatMenu({ onChat }: { onChat?: (phraseId: string) => boolean | void }) {
  const [open, setOpen] = useState(false);
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (until <= Date.now()) return;
    const id = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= until) clearInterval(id);
    }, 250);
    return () => clearInterval(id);
  }, [until]);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const left = Math.max(0, Math.ceil((until - now) / 1000));
  const send = (id: string) => {
    setOpen(false);
    if (onChat?.(id) === false) return;
    const t = Date.now();
    setNow(t);
    setUntil(t + CHAT_COOLDOWN_MS);
  };

  return (
    <div className="chat-wrap" ref={wrap}>
      {open && (
        <div className="chat-menu" role="menu" aria-label="Chọn câu chat">
          {CHAT_PHRASES.map((p) => (
            <button key={p.id} type="button" role="menuitem" onClick={() => send(p.id)}>
              {p.text}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        className="chat-toggle tool"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={!onChat || left > 0}
        onClick={() => setOpen((v) => !v)}
      >
        💬 {left > 0 ? `${left}s` : "Chat"}
      </button>
    </div>
  );
}

export function GameTable({ game, seats, canAct, error, onPlay, onPass, chats, onChat, clockOffset = 0 }: Props) {
  const state = game.state;
  const me = state.yourSeat ?? 0;
  const compact = useMediaQuery("(max-width: 600px)");
  const [selected, setSelected] = useState<number[]>([]);
  const [sortMode, setSortMode] = useState<SortMode>("rank");
  const [log, setLog] = useState<string[]>([]);
  const name = useMemo(
    () => (seat: number) => (seat === me ? "Bạn" : (seats[seat]?.nickname ?? `Ghế ${seat + 1}`)),
    [seats, me],
  );

  const hand = useMemo(() => sortHand(state.yourHand ?? [], sortMode), [state.yourHand, sortMode]);
  // Bỏ chọn những lá không còn trên tay (vd vừa đánh xong hoặc server tự đánh khi hết giờ).
  useEffect(() => setSelected((prev) => prev.filter((c) => state.yourHand?.includes(c))), [state.yourHand]);
  useEffect(() => {
    const lines = game.events.map((e) => describeEvent(e, name)).filter((l): l is string => l !== null);
    if (lines.length) setLog((prev) => [...lines.reverse(), ...prev].slice(0, 8));
  }, [game.events, name]);

  const secondsLeft = useSecondsLeft(state.turnDeadline, clockOffset);
  const myTurn = state.current === me;

  // Hiệu ứng "nè !!!" khi có người đánh tứ quý / đôi thông. Bỏ qua bài đã có sẵn lúc mới vào bàn / kết nối lại.
  const playKey = state.trick.top ? `${state.trick.topSeat}:${state.trick.top.join(",")}` : "";
  const lastPlayKey = useRef(playKey);
  const burstTimer = useRef<number | undefined>(undefined);
  const [burst, setBurst] = useState<{ id: string; text: string; who: string } | null>(null);
  useEffect(() => () => window.clearTimeout(burstTimer.current), []);
  useEffect(() => {
    if (playKey === lastPlayKey.current) return;
    lastPlayKey.current = playKey;
    const label = playKey ? specialPlayLabel(state.trick.topCombo, state.trick.top ?? []) : null;
    if (!label) return;
    setBurst({ id: playKey, text: `${label} nè !!!`, who: name(state.trick.topSeat ?? 0) });
    window.clearTimeout(burstTimer.current);
    burstTimer.current = window.setTimeout(() => setBurst(null), 1900);
  }, [playKey, name, state.trick.top, state.trick.topCombo, state.trick.topSeat]);
  // Bài vừa đánh bay vào từ phía người đánh (0 = bạn, 1 = trái, 2 = trên, 3 = phải).
  const fromPos = ["me", "left", "top", "right"][(((state.trick.topSeat ?? me) - me) % 4 + 4) % 4];
  const leading = state.trick.top === null;
  // Vị trí theo chiều kim đồng hồ: người kế tiếp bên trái, đối diện ở trên, người trước bên phải.
  const others = [1, 2, 3].map((offset) => (me + offset) % 4);
  // Chọn nhiều lá: bấm từng lá, hoặc nhấn giữ rồi kéo ngang qua các lá (chuột / cảm ứng) để chọn / bỏ chọn cả dải.
  const drag = useRef<{ start: number; select: boolean; base: number[]; moved: boolean } | null>(null);
  const skipClick = useRef(false);
  const cardIndexAt = (x: number, y: number): number | null => {
    const el = document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-card-idx]");
    return el ? Number(el.dataset.cardIdx) : null;
  };
  const onHandDown = (e: ReactPointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const idx = cardIndexAt(e.clientX, e.clientY);
    if (idx === null || hand[idx] === undefined) return;
    drag.current = { start: idx, select: !selected.includes(hand[idx]!), base: selected, moved: false };
  };
  const onHandMove = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    if (e.pointerType === "mouse" && e.buttons === 0) {
      drag.current = null; // nhả chuột bên ngoài vùng bài
      return;
    }
    const idx = cardIndexAt(e.clientX, e.clientY);
    if (idx === null || (idx === d.start && !d.moved)) return;
    d.moved = true;
    const range = hand.slice(Math.min(d.start, idx), Math.max(d.start, idx) + 1);
    setSelected(d.select ? [...new Set([...d.base, ...range])] : d.base.filter((c) => !range.includes(c)));
  };
  const onHandUp = () => {
    if (drag.current?.moved) {
      skipClick.current = true; // lần click ngay sau khi kéo không được đảo lại lá đầu dải
      window.setTimeout(() => (skipClick.current = false), 0);
    }
    drag.current = null;
  };
  const toggle = (card: number) => {
    if (skipClick.current) return;
    setSelected((prev) => (prev.includes(card) ? prev.filter((c) => c !== card) : [...prev, card]));
  };

  return (
    <section className={`game-table${myTurn ? " my-turn" : ""}`} aria-label="Bàn chơi">
      {burst && <PlayBurst key={burst.id} text={burst.text} who={burst.who} />}
      <div className="opponents">
        {others.map((seat, i) => {
          const p = state.players[seat]!;
          return (
            <div
              key={seat}
              className={`opponent pos-${["left", "top", "right"][i]}${state.current === seat ? " turn" : ""}`}
            >
              <span className="avatar" aria-hidden="true">
                {name(seat).charAt(0).toUpperCase()}
              </span>
              {chats?.[seat] && (
                <SpeechBubble key={chats[seat]!.key} phrase={chats[seat]!.phrase} tail={["left", "side", "right"][i] as "left" | "side" | "right"} />
              )}
              <strong className="opponent-name">{name(seat)}</strong>
              {p.cardCount === 1 && p.status === "ACTIVE" && (
                <span className="last-card" role="status">
                  ⚠ Còn 1 lá!
                </span>
              )}
              <span className="muted small">
                {p.status === "CONG" ? "Cóng (bét)" : p.rank ? RANK_LABEL[p.rank] : STATUS_LABEL[p.status]}
                {state.trick.passed.includes(seat) && " · Đã bỏ lượt"}
                {seats[seat] && !seats[seat]!.connected && " · ⟳ mất kết nối"}
              </span>
            </div>
          );
        })}
      </div>

      <div className="trick" aria-live="polite">
        {state.trick.top ? (
          <>
            <div className={`trick-cards from-${fromPos}`} key={playKey}>
              {state.trick.top.map((c) => (
                <CardFace key={c} card={c} />
              ))}
            </div>
            <div className="muted small">
              {comboLabel(state.trick.topCombo)} của {name(state.trick.topSeat ?? 0)}
              {state.trick.chainValue > 0 && <strong className="warn"> · Chặt chồng {state.trick.chainValue} điểm</strong>}
            </div>
          </>
        ) : (
          <div className="muted">
            {name(state.trick.leader)} mở vòng
            {state.firstMovePending && state.openingMode === "THREE_CLUBS" && " (phải có 3♣)"}
          </div>
        )}
      </div>

      {/* Avatar của mình ở giữa phía dưới. PC: nút chat bên trái avatar; mobile: nút chat ở hàng nút hành động. */}
      <div className="my-seat">
        {!compact && <ChatMenu onChat={onChat} />}
        <div className="my-avatar">
          <span className="avatar-wrap">
            {chats?.[me] && <SpeechBubble key={chats[me]!.key} phrase={chats[me]!.phrase} tail="side" />}
            <span className="avatar" aria-hidden="true">
              {(seats[me]?.nickname ?? "B").charAt(0).toUpperCase()}
            </span>
          </span>
          <span className="my-name">Bạn</span>
        </div>
      </div>

      <div className={`turn-bar${myTurn ? " mine" : ""}`}>
        {state.current !== null && (
          <>
            {myTurn ? "LƯỢT CỦA BẠN" : `Lượt của ${name(state.current)}`}
            {secondsLeft !== null && <span className={secondsLeft <= 5 ? "warn" : ""}> · ⏱ {secondsLeft}s</span>}
          </>
        )}
      </div>

      {error && (
        <p role="alert" className="error game-error">
          {error}
        </p>
      )}

      <div className="actions game-actions">
        <button type="button" className="pass" onClick={onPass} disabled={!canAct || !myTurn || leading}>
          Bỏ lượt
        </button>
        <button
          type="button"
          className="primary play"
          disabled={!canAct || !selected.length}
          onClick={() => {
            onPlay(selected);
          }}
        >
          Đánh {selected.length ? `(${selected.length})` : ""}
        </button>
        <button type="button" className="tool" onClick={() => setSortMode(sortMode === "rank" ? "suit" : "rank")}>
          Xếp theo {sortMode === "rank" ? "chất" : "số"}
        </button>
        <button type="button" className="tool" onClick={() => setSelected([])} disabled={!selected.length}>
          Bỏ chọn
        </button>
        {compact && <ChatMenu onChat={onChat} />}
      </div>

      <div
        className="my-hand"
        aria-label="Bài của bạn"
        onPointerDown={onHandDown}
        onPointerMove={onHandMove}
        onPointerUp={onHandUp}
        onPointerCancel={onHandUp}
      >
        {hand.map((card, i) => (
          <CardFace key={card} card={card} index={i} selected={selected.includes(card)} onClick={() => toggle(card)} />
        ))}
      </div>

      <ol className="game-log muted small" aria-label="Diễn biến">
        {log.map((line, i) => (
          <li key={`${i}-${line}`}>{line}</li>
        ))}
      </ol>
      <p className="muted small game-foot">
        Luật v{game.rules.version} · mã kiểm chứng bộ bài {game.deckCommitment.slice(0, 10)}…
      </p>
    </section>
  );
}
