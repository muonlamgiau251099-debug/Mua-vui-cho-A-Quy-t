import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import type { SeatState } from "../api/guest";
import { COMPACT_QUERY, useMediaQuery } from "../lib/useMediaQuery";
import {
  cardLabel,
  cardsLabel,
  comboLabel,
  insertionIndex,
  isRed,
  moveCard,
  rankLabel,
  rankOf,
  sortHand,
  suitSymbol,
  suitOf,
  type SortMode,
} from "./cards";
import { Modal } from "./Modal";
import {
  CHAT_COOLDOWN_MS,
  CHAT_MAX_LENGTH,
  CHAT_PHRASES,
  cleanChatText,
  type ChatBubbles,
  type ChatOutgoing,
} from "./chat";
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
  onChat?: (msg: ChatOutgoing) => boolean | void; // trả false nếu chưa gửi được (mất kết nối)
  info?: ReactNode; // màn hình nhỏ: nội dung popup "Thông tin" (điểm phiên, xếp hạng)
  onLeave?: () => void; // màn hình nhỏ: nút "Rời phòng" (có popup xác nhận)
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

type CardFaceProps = { card: number; selected?: boolean; dragging?: boolean; index?: number; onClick?: () => void };

function CardFace({ card, selected, dragging, index, onClick }: CardFaceProps) {
  const className = `card${isRed(card) ? " red" : ""}${selected ? " selected" : ""}${dragging ? " dragging" : ""}`;
  return onClick ? (
    <button type="button" className={className} aria-pressed={selected} data-card-idx={index} onClick={onClick}>
      {cardLabel(card)}
    </button>
  ) : (
    <span className={className} role="img" aria-label={cardLabel(card)} data-suit={suitSymbol(card)}>
      <span className="rk">{rankLabel(card)}</span>
      <span className="st">{suitSymbol(card)}</span>
    </span>
  );
}

/** Bong bóng chat kiểu pixel, hiện ra từ avatar người gửi. */
function SpeechBubble({ text, tail }: { text: string; tail: "left" | "right" | "side" }) {
  // left/right: bong bóng nằm trên avatar, đuôi chỉ xuống avatar; side: nằm bên phải avatar, đuôi chỉ sang trái.
  return (
    <div className={`chat-bubble tail-${tail}`} role="status">
      {text}
    </div>
  );
}

const SendIcon = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
    <path d="M3.4 20.4 21 12 3.4 3.6 3.3 10.1 15 12 3.3 13.9z" fill="currentColor" />
  </svg>
);

/** Card kéo lên từ dưới (~60% màn hình): ô nhập chữ tự do + nút gửi, bên dưới là các câu có sẵn. */
function ChatSheet({ onSend, onClose }: { onSend: (msg: ChatOutgoing) => void; onClose: () => void }) {
  const [text, setText] = useState("");
  const clean = cleanChatText(text);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="sheet-backdrop" role="presentation" onClick={onClose}>
      <div className="chat-sheet" role="dialog" aria-modal="true" aria-label="Chat" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-handle" aria-hidden="true" />
        <form
          className="chat-compose"
          onSubmit={(e) => {
            e.preventDefault();
            if (clean) onSend({ text: clean });
          }}
        >
          <input
            value={text}
            maxLength={CHAT_MAX_LENGTH}
            placeholder="Nhập tin nhắn…"
            aria-label="Tin nhắn"
            autoComplete="off"
            enterKeyHint="send"
            onChange={(e) => setText(e.target.value)}
          />
          <button type="submit" className="send-btn" aria-label="Gửi" disabled={!clean}>
            <SendIcon />
          </button>
        </form>
        <p className="chat-count small muted" aria-hidden="true">
          {Array.from(text).length}/{CHAT_MAX_LENGTH}
        </p>
        <p className="chat-section small muted">Câu có sẵn</p>
        <div className="chat-presets" role="group" aria-label="Câu chat có sẵn">
          {CHAT_PHRASES.map((p) => (
            <button key={p.id} type="button" onClick={() => onSend({ phrase: p.id })}>
              {p.text}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Nút chat: mở card chat, khóa 10 giây sau mỗi lần gửi. */
function ChatMenu({ onChat }: { onChat?: (msg: ChatOutgoing) => boolean | void }) {
  const [open, setOpen] = useState(false);
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (until <= Date.now()) return;
    const id = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= until) clearInterval(id);
    }, 250);
    return () => clearInterval(id);
  }, [until]);

  const left = Math.max(0, Math.ceil((until - now) / 1000));
  const send = (msg: ChatOutgoing) => {
    if (onChat?.(msg) === false) return; // chưa gửi được (mất kết nối): giữ card mở để thử lại
    setOpen(false);
    const t = Date.now();
    setNow(t);
    setUntil(t + CHAT_COOLDOWN_MS);
  };

  return (
    <div className="chat-wrap">
      <button
        type="button"
        className="chat-toggle tool"
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={!onChat || left > 0}
        onClick={() => setOpen(true)}
      >
        💬 {left > 0 ? `${left}s` : "Chat"}
      </button>
      {open && createPortal(<ChatSheet onSend={send} onClose={() => setOpen(false)} />, document.body)}
    </div>
  );
}

/** Kích thước một lá trên màn hình (để vẽ lá đang kéo đúng cỡ). */
const cardSize = (el: HTMLElement) => {
  const r = el.getBoundingClientRect();
  return { w: r.width, h: r.height };
};

type Gesture =
  | { kind: "reorder"; idx: number; card: number; x0: number; y0: number; centers: number[] | null; active: boolean; to: number; w: number; h: number }
  | { kind: "sweep"; start: number; select: boolean; base: number[]; moved: boolean };

export function GameTable({ game, seats, canAct, error, onPlay, onPass, chats, onChat, info, onLeave, clockOffset = 0 }: Props) {
  const state = game.state;
  const me = state.yourSeat ?? 0;
  const compact = useMediaQuery(COMPACT_QUERY);
  const [selected, setSelected] = useState<number[]>([]);
  const [sortMode, setSortMode] = useState<SortMode>("rank");
  const [custom, setCustom] = useState<number[] | null>(null); // thứ tự do người chơi tự kéo thả; null = tự xếp
  const [infoOpen, setInfoOpen] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const name = useMemo(
    () => (seat: number) => (seat === me ? "Bạn" : (seats[seat]?.nickname ?? `Ghế ${seat + 1}`)),
    [seats, me],
  );

  const hand = useMemo(() => {
    const base = sortHand(state.yourHand ?? [], sortMode);
    if (!custom) return base;
    const have = new Set(base);
    const kept = custom.filter((c) => have.has(c)); // bỏ những lá đã đánh
    const keptSet = new Set(kept);
    return [...kept, ...base.filter((c) => !keptSet.has(c))];
  }, [state.yourHand, sortMode, custom]);
  // Ván mới: về lại thứ tự tự xếp.
  useEffect(() => setCustom(null), [game.gameId]);
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
  // Tương tác với bài trên tay:
  //  - bấm từng lá để chọn / bỏ chọn;
  //  - kéo một lá sang vị trí khác để tự xếp bài (giữ nguyên cho tới khi bấm "Xếp theo ...");
  //  - quét ngang trên vùng trống phía trên hàng bài để chọn / bỏ chọn cả dải lá.
  const gesture = useRef<Gesture | null>(null);
  const handRef = useRef<HTMLDivElement>(null);
  const skipClick = useRef(false);
  const [drag, setDrag] = useState<{ card: number; x: number; y: number; to: number; w: number; h: number } | null>(null);
  const shownHand = drag ? moveCard(hand, hand.indexOf(drag.card), drag.to) : hand;

  const cardEls = () => Array.from(handRef.current?.querySelectorAll<HTMLElement>("[data-card-idx]") ?? []);
  const indexAtX = (x: number): number | null => {
    let found: number | null = null;
    for (const el of cardEls()) {
      const r = el.getBoundingClientRect();
      if (x >= r.left && x <= r.right) found = Number(el.dataset.cardIdx); // lá bên phải nằm đè lên lá bên trái
    }
    return found;
  };
  const suppressClick = () => {
    skipClick.current = true; // click ngay sau khi kéo không được đảo lại lá vừa kéo
    window.setTimeout(() => (skipClick.current = false), 0);
  };
  const onHandDown = (e: ReactPointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-card-idx]");
    const idx = el ? Number(el.dataset.cardIdx) : indexAtX(e.clientX);
    const card = idx === null ? undefined : hand[idx];
    if (idx === null || card === undefined) return;
    if (el && e.clientY >= el.getBoundingClientRect().top) {
      gesture.current = { kind: "reorder", idx, card, x0: e.clientX, y0: e.clientY, centers: null, active: false, to: idx, ...cardSize(el) };
      el.setPointerCapture?.(e.pointerId);
    } else {
      gesture.current = { kind: "sweep", start: idx, select: !selected.includes(card), base: selected, moved: false };
    }
  };
  const onHandMove = (e: ReactPointerEvent) => {
    const g = gesture.current;
    if (!g) return;
    if (e.pointerType === "mouse" && e.buttons === 0) {
      gesture.current = null; // nhả chuột bên ngoài vùng bài
      setDrag(null);
      return;
    }
    if (g.kind === "sweep") {
      const idx = indexAtX(e.clientX);
      if (idx === null || (idx === g.start && !g.moved)) return;
      g.moved = true;
      const range = hand.slice(Math.min(g.start, idx), Math.max(g.start, idx) + 1);
      setSelected(g.select ? [...new Set([...g.base, ...range])] : g.base.filter((c) => !range.includes(c)));
      return;
    }
    if (!g.active) {
      if (Math.hypot(e.clientX - g.x0, e.clientY - g.y0) < 6) return; // chưa đủ xa: vẫn là một cú bấm
      g.active = true;
      g.centers = cardEls().map((el) => {
        const r = el.getBoundingClientRect();
        return (r.left + r.right) / 2;
      });
    }
    g.to = insertionIndex(g.centers ?? [], g.idx, e.clientX);
    setDrag({ card: g.card, x: e.clientX, y: e.clientY, to: g.to, w: g.w, h: g.h });
  };
  const onHandUp = () => {
    const g = gesture.current;
    gesture.current = null;
    if (!g) return;
    if (g.kind === "sweep") {
      if (g.moved) suppressClick();
      return;
    }
    if (g.active) {
      setCustom(moveCard(hand, g.idx, g.to));
      suppressClick();
    }
    setDrag(null);
  };
  const onHandCancel = () => {
    gesture.current = null;
    setDrag(null);
  };
  const toggle = (card: number) => {
    if (skipClick.current) return;
    setSelected((prev) => (prev.includes(card) ? prev.filter((c) => c !== card) : [...prev, card]));
  };

  return (
    <section className={`game-table${compact ? " compact" : ""}${myTurn ? " my-turn" : ""}`} aria-label="Bàn chơi">
      {burst && <PlayBurst key={burst.id} text={burst.text} who={burst.who} />}
      {compact && (
        <>
          <button type="button" className="table-btn info-btn" onClick={() => setInfoOpen(true)}>
            ⓘ Thông tin
          </button>
          {onLeave && (
            <button type="button" className="table-btn leave-btn danger" onClick={() => setLeaveOpen(true)}>
              Rời phòng
            </button>
          )}
        </>
      )}
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
                <SpeechBubble key={chats[seat]!.key} text={chats[seat]!.text} tail={["left", "side", "right"][i] as "left" | "side" | "right"} />
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
            <div className={`trick-cards from-${fromPos}`} data-n={state.trick.top.length} style={{ "--n": state.trick.top.length } as CSSProperties} key={playKey}>
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
            {chats?.[me] && <SpeechBubble key={chats[me]!.key} text={chats[me]!.text} tail="side" />}
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
        <button
          type="button"
          className="tool"
          onClick={() => {
            setCustom(null); // quay về tự xếp
            setSortMode(sortMode === "rank" ? "suit" : "rank");
          }}
        >
          Xếp theo {sortMode === "rank" ? "chất" : "số"}
        </button>
        <button type="button" className="tool" onClick={() => setSelected([])} disabled={!selected.length}>
          Bỏ chọn
        </button>
        {compact && <ChatMenu onChat={onChat} />}
      </div>

      <div
        className="my-hand"
        ref={handRef}
        aria-label="Bài của bạn"
        onPointerDown={onHandDown}
        onPointerMove={onHandMove}
        onPointerUp={onHandUp}
        onPointerCancel={onHandCancel}
      >
        {shownHand.map((card, i) => (
          <CardFace
            key={card}
            card={card}
            index={i}
            dragging={drag?.card === card}
            selected={selected.includes(card)}
            onClick={() => toggle(card)}
          />
        ))}
      </div>

      {/* Lá đang kéo vẽ ra ngoài khung bài (portal): khung bài dùng container query nên không chứa được phần tử fixed. */}
      {drag &&
        createPortal(
          <div
            className={`card drag-ghost${isRed(drag.card) ? " red" : ""}`}
            style={{ left: drag.x, top: drag.y, width: drag.w, height: drag.h }}
            aria-hidden="true"
          >
            {cardLabel(drag.card)}
          </div>,
          document.body,
        )}

      <ol className="game-log muted small" aria-label="Diễn biến">
        {log.map((line, i) => (
          <li key={`${i}-${line}`}>{line}</li>
        ))}
      </ol>
      {!compact && (
        <p className="muted small game-foot">
          Luật v{game.rules.version} · mã kiểm chứng bộ bài {game.deckCommitment.slice(0, 10)}…
        </p>
      )}

      {infoOpen && (
        <Modal title="Thông tin" onClose={() => setInfoOpen(false)}>
          {info}
          <p className="muted small">
            Luật v{game.rules.version} · mã kiểm chứng bộ bài {game.deckCommitment.slice(0, 10)}…
          </p>
        </Modal>
      )}
      {leaveOpen && onLeave && (
        <Modal title="Rời phòng?" onClose={() => setLeaveOpen(false)}>
          <p>Rời phòng khi đang chơi sẽ bị xử thua (xếp bét). Vẫn rời?</p>
          <div className="dialog-actions">
            <button type="button" onClick={() => setLeaveOpen(false)}>
              Ở lại
            </button>
            <button
              type="button"
              className="danger"
              onClick={() => {
                setLeaveOpen(false);
                onLeave();
              }}
            >
              Rời phòng
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
