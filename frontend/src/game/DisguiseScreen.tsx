import { useEffect, useState, useSyncExternalStore } from "react";
import { COMPACT_QUERY, useMediaQuery } from "../lib/useMediaQuery";
import type { LiveGame } from "./types";
import "./disguise.css";

/**
 * Thông tin lượt chơi để ô số báo ngầm. Màn hình ngụy trang nằm ở gốc ứng dụng (dùng được ở mọi màn),
 * còn ván chỉ có ở RoomPage nên RoomPage "đăng" trạng thái lượt vào đây.
 */
export type DisguiseTurn = { myTurn: boolean; deadline: number | null; clockOffset: number };
const NO_TURN: DisguiseTurn = { myTurn: false, deadline: null, clockOffset: 0 };
let turn: DisguiseTurn = NO_TURN;
const listeners = new Set<() => void>();

export function setDisguiseTurn(next: DisguiseTurn): void {
  if (next.myTurn === turn.myTurn && next.deadline === turn.deadline && next.clockOffset === turn.clockOffset) return;
  turn = next;
  listeners.forEach((l) => l());
}

export function turnFromGame(game: LiveGame | null, clockOffset: number): DisguiseTurn {
  const st = game?.state;
  const myTurn = !!st && st.yourSeat != null && st.current === st.yourSeat;
  return myTurn ? { myTurn, deadline: st.turnDeadline, clockOffset } : NO_TURN;
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};

/** Phím ↓ / ↑ chỉ có tác dụng khi người dùng không đang gõ chữ (chat, ô nhập…). */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

const FOLDERS: { name: string; count?: number; bracket?: number; active?: boolean; icon: string }[] = [
  { name: "Inbox", icon: "▣", active: true },
  { name: "Drafts", bracket: 3, icon: "✎" },
  { name: "Sent Items", icon: "➤" },
  { name: "Deleted Items", count: 34, icon: "🗑" },
  { name: "Junk Email", icon: "⊘" },
  { name: "Notes", bracket: 2, icon: "▤" },
  { name: "Archive", icon: "▭" },
  { name: "Conversation Hist...", icon: "▭" },
  { name: "Free.co.jp", count: 682, icon: "▭" },
  { name: "Lenovo", count: 780, icon: "▭" },
  { name: "Search Folders", icon: "▭" },
];

const MAILS: { from: string; subject: string; preview: string; date: string; initials?: string; color?: string; selected?: boolean; blue?: boolean }[] = [
  { from: "Tanaka Hiroshi", subject: "【重要】年末調整の入力のお願い…", preview: "各位 お疲れ様です。 HRより2026年…", date: "Fri 11/6", selected: true },
  { from: "IT-ISM HO RK", subject: "[Thông báo bảo trì] GitLab ...", preview: "（日本語版は下記をご参照くださ…", date: "Fri 11/6", initials: "IR", color: "#7b4fe0" },
  { from: "Rikkeisoft GitLab", subject: "Your personal access token...", preview: "Hi Nguyen Van An! One or more ...", date: "Fri 11/6", initials: "RG", color: "#b9d4ee" },
  { from: "Sato Kenji", subject: "Weekly sync notes", preview: "invited you to edit a...", date: "Thu 11/5", initials: "SK", color: "#2e8b8b" },
  { from: "Suzuki Aiko", subject: "Manufacturing AI MTG", preview: "No preview is available.", date: "Thu 11/5", initials: "SA", color: "#c2563d", blue: true },
  { from: "IT-ISM HO RK", subject: "[Cảnh báo ATTT] Phòng v...", preview: "（日本語版は下記をご参照くださ…", date: "Thu 11/5", initials: "IR", color: "#7b4fe0", blue: true },
];

const RIBBON: [string, string][] = [
  ["New", "✉"], ["Delete", "🗑"], ["Archive", "▭"], ["Reply", "↩"], ["Reply all", "↩↩"], ["Forward", "↪"],
  ["Meeting", "▦"], ["Share to Teams", "⊞"], ["Sweep", "✦"], ["Move", "⇥"], ["Rules", "☰"], ["Read / Unread", "✉"],
  ["Categorize", "◇"], ["Flag", "⚑"], ["Pin", "📌"], ["Snooze", "◷"], ["Policy", "▤"], ["Print", "⎙"],
];

/**
 * Màn hình "ngụy trang" giả giao diện Outlook (chỉ PC). Phủ lên toàn bộ trang để che bàn chơi tạm thời;
 * không đụng đến ván đấu (WebSocket, đồng hồ lượt… vẫn chạy bình thường bên dưới).
 * Ô số 1649 bên cạnh "Inbox" báo ngầm trạng thái: xanh = chưa tới lượt, đỏ nhấp nháy + số giây = đang tới lượt bạn.
 */
export function DisguiseScreen() {
  const { myTurn, deadline, clockOffset } = useSyncExternalStore(subscribe, () => turn);
  const compact = useMediaQuery(COMPACT_QUERY); // chỉ dành cho PC
  const [on, setOn] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || isTyping(e.target)) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setOn(true);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setOn(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Đổi tiêu đề tab cho giống Outlook trong lúc ngụy trang.
  useEffect(() => {
    if (!on) return;
    const old = document.title;
    document.title = "Mail - Outlook";
    return () => {
      document.title = old;
    };
  }, [on]);

  useEffect(() => {
    if (!on) return;
    const id = setInterval(() => setNow(Date.now() / 1000), 250);
    return () => clearInterval(id);
  }, [on]);

  if (!on || compact) return null;

  const seconds = myTurn ? Math.max(0, Math.ceil((deadline ?? now + clockOffset) - (now + clockOffset))) : null;
  const badge = (
    <span
      className={`ol-badge${myTurn ? " ol-turn" : ""}`}
      data-testid="ol-badge"
      aria-label={myTurn ? `${seconds} unread` : "1649 unread"}
    >
      {myTurn ? seconds : 1649}
    </span>
  );

  return (
    <div className="ol" data-testid="disguise" aria-label="Outlook">
      <header className="ol-top">
        <span className="ol-grid">⋮⋮⋮</span>
        <b className="ol-brand">Outlook</b>
        <div className="ol-search">⌕ Search</div>
        <span className="ol-top-right">🔔 &nbsp; ⋯ &nbsp; <i className="ol-me" /></span>
      </header>

      <div className="ol-body">
        <nav className="ol-rail" aria-hidden="true">
          {["#0f6cbd", "#2b88d8", "#d9534f", "#5b5fc7", "#2a6fdb", "#0f6cbd", "#3b9ae1", "#7a7a7a"].map((c, i) => (
            <span key={i} style={{ background: c }} />
          ))}
        </nav>

        <div className="ol-main">
          <div className="ol-tabs">
            <span>☰</span>
            <span>File</span>
            <span className="on">Home</span>
            <span>View</span>
            <span>Help</span>
            <span className="ol-next">
              【リッケイ名古屋】朝会
              <small>Tomorrow 9:15 AM Microsof...</small>
            </span>
          </div>

          <div className="ol-ribbon">
            {RIBBON.map(([label, icon]) => (
              <span key={label} className="ol-btn">
                <i>{icon}</i>
                {label}
              </span>
            ))}
            <span className="ol-copilot">
              <i>◐</i>Copilot
            </span>
          </div>

          <div className="ol-cols">
            <aside className="ol-folders">
              <div className="ol-fav">▾ Favorites</div>
              <div className="ol-folder">
                <span className="ic">▣</span>Inbox{badge}
              </div>
              <div className="ol-folder">
                <span className="ic">➤</span>Sent Items
              </div>
              <div className="ol-folder">
                <span className="ic">✎</span>Drafts<em>[3]</em>
              </div>
              <div className="ol-fav ol-acct">▾ <span className="ol-redact">nguyen.van.an@example.com</span></div>
              {FOLDERS.map((f) => (
                <div key={f.name} className={`ol-folder${f.active ? " active" : ""}`}>
                  <span className="ic">{f.icon}</span>
                  {f.name}
                  {f.active ? badge : f.count ? <span className="ol-num">{f.count}</span> : f.bracket ? <em>[{f.bracket}]</em> : null}
                </div>
              ))}
            </aside>

            <section className="ol-list">
              <div className="ol-list-head">
                <b>Focused</b>
                <span>Other</span>
              </div>
              <div className="ol-other">Other Emails (99+) <small>Tuyển Dụng Rikkeisoft, Văn hóa Truyền t...</small></div>
              <div className="ol-week">▾ Last Week</div>
              {MAILS.map((m, i) => (
                <div key={i} className={`ol-mail${m.selected ? " sel" : ""}`}>
                  <span className="av" style={{ background: m.color ?? "transparent" }}>
                    {m.initials ?? ""}
                  </span>
                  <div className="tx">
                    <div className="r1">
                      <b className={m.blue ? "blue" : undefined}>{m.from}</b>
                    </div>
                    <div className="r2">
                      <span className={m.blue ? "blue" : undefined}>{m.subject}</span>
                      <small>{m.date}</small>
                    </div>
                    <div className="r3">{m.preview}</div>
                  </div>
                </div>
              ))}
            </section>

            <article className="ol-read">
              <h2>
                【重要】年末調整の入力のお願い（締切：11月25日 18:00まで）
                <span className="ol-sum">Summarize this email</span>
              </h2>
              <div className="ol-card">
                <div className="ol-from">
                  <span className="av big" />
                  <div>
                    <b>Tanaka Hiroshi</b>
                    <div className="to">To: <span className="ok" />Yoshino Momoka (芳野 桃花)</div>
                    <div className="to">Cc: Suzuki Aiko; Sato Kenji; Yamada Taro; Nakamura Yui; Kobayashi Ren</div>
                  </div>
                  <small>Fri 11/6/2026 5:23 PM</small>
                </div>
                <div className="ol-text">
                  <p>各位</p>
                  <p>お疲れ様です。<br />HRより2026年度の年末調整でまだ入力が完了されていない方へご案内です。</p>
                  <p>freeeより年末調整の入力案内メールが送付されておりますので、<br />内容をご確認のうえ、期限までに入力作業を完了させていただけますようお願いいたします。</p>
                  <p><mark>■ 入力締切</mark><br /><mark className="red">2026年11月25日（水）18:00 まで</mark></p>
                  <p>【注意事項】<br />freeeからの案内メールが届いていない、または不明な点がある場合は<br />hr-support@example.com までご連絡ください。</p>
                  <p>期限を過ぎた場合、手続きに遅れが生じる可能性がございますのでお早めのご対応をお願いいたします。<br />お忙しいところ恐縮ですが、ご協力のほどよろしくお願い申し上げます。</p>
                </div>
              </div>
            </article>
          </div>
        </div>
      </div>
    </div>
  );
}
