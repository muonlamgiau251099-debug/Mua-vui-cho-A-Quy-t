import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ApiError, errorMessage } from "../api/client";
import { guestApi, historyApi, roomApi } from "../api/guest";

export function LobbyPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["guest", "me"], queryFn: guestApi.me });
  const [editing, setEditing] = useState(false);
  const [newName, setNewName] = useState("");
  const [code, setCode] = useState("");
  const sessions = useQuery({ queryKey: ["guest", "sessions"], queryFn: historyApi.mySessions, enabled: !!me.data });
  const rename = useMutation({
    mutationFn: () => guestApi.rename(newName),
    onSuccess: (profile) => {
      queryClient.setQueryData(["guest", "me"], profile); // tên mới hiện ngay, token giữ nguyên
      setEditing(false);
    },
  });
  const create = useMutation({
    mutationFn: roomApi.create,
    onSuccess: (room) => navigate(`/r/${room.code}`),
    onError: (e) => {
      if (e instanceof ApiError && typeof e.body.roomCode === "string") navigate(`/r/${e.body.roomCode}`);
    },
  });

  if (me.isLoading) return <main className="app">Đang tải…</main>;
  if (!me.data) return <Navigate to="/?next=/lobby" replace />;

  const join = (e: FormEvent) => {
    e.preventDefault();
    const clean = code.trim().toUpperCase();
    if (clean) navigate(`/r/${clean}`);
  };

  return (
    <main className="app lobby">
      <header className="lobby-head">
        <Link to="/" className="back">
          ← Trang chủ
        </Link>
        <h1>Sảnh chờ</h1>
        {editing ? (
          <form
            className="rename-form"
            onSubmit={(e) => {
              e.preventDefault();
              rename.mutate();
            }}
          >
            <label htmlFor="new-nickname" className="sr-only">
              Tên hiển thị mới
            </label>
            <input
              id="new-nickname"
              value={newName}
              maxLength={20}
              autoComplete="nickname"
              placeholder="Tên mới"
              onChange={(e) => setNewName(e.target.value)}
              required
            />
            <button
              type="submit"
              className="primary"
              disabled={rename.isPending || newName.trim().length < 2 || newName.trim() === me.data.nickname}
            >
              {rename.isPending ? "Đang lưu…" : "Lưu"}
            </button>
            <button type="button" onClick={() => setEditing(false)}>
              Hủy
            </button>
          </form>
        ) : (
          <p className="muted">
            Bạn: <strong className="accent-text">{me.data.nickname}</strong>{" "}
            {!me.data.currentRoom && (
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  rename.reset();
                  setNewName(me.data!.nickname);
                  setEditing(true);
                }}
              >
                ✎ Đổi tên
              </button>
            )}
          </p>
        )}
        {rename.error && (
          <p role="alert" className="error">
            {errorMessage(rename.error)}
          </p>
        )}
      </header>

      {me.data.currentRoom ? (
        <section className="panel">
          <p>Bạn đang ngồi ở phòng {me.data.currentRoom.code}.</p>
          <button className="primary lg" onClick={() => navigate(`/r/${me.data!.currentRoom!.code}`)}>
            Vào phòng
          </button>
        </section>
      ) : (
        <div className="lobby-actions">
          <section className="panel">
            <h2>Tạo phòng</h2>
            <p className="muted small">Tạo phòng mới rồi gửi mã hoặc link mời cho bạn bè.</p>
            <button className="primary lg" onClick={() => create.mutate()} disabled={create.isPending}>
              {create.isPending ? "Đang tạo…" : "Tạo phòng mới"}
            </button>
            {create.error && (
              <p role="alert" className="error">
                {errorMessage(create.error)}
              </p>
            )}
          </section>
          <form className="panel form" onSubmit={join}>
            <h2>Vào phòng</h2>
            <label htmlFor="room-code">Hoặc nhập mã phòng</label>
            <div className="join-row">
              <input
                id="room-code"
                className="code-input"
                value={code}
                maxLength={6}
                placeholder="VD: K7QX2M"
                autoCapitalize="characters"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
              />
              <button type="submit" className="primary" disabled={code.trim().length !== 6}>
                Vào phòng
              </button>
            </div>
          </form>
        </div>
      )}

      {sessions.data && sessions.data.items.length > 0 && (
        <section className="recent">
          <h2>Phiên gần đây</h2>
          <ul className="session-cards">
            {sessions.data.items.map((s) => (
              <li key={s.sessionId}>
                <Link to={`/history/${s.sessionId}`} className="session-item">
                  <span className="session-title">
                    Phòng {s.roomCode} · phiên {s.sessionNo}
                    {s.status === "ACTIVE" && <span className="badge">Đang chơi</span>}
                  </span>
                  <span className="muted small">
                    {s.gamesPlayed} ván · dẫn đầu: {s.standings[0]?.nickname} ({s.standings[0]?.total})
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
