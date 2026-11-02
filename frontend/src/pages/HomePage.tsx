import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { guestApi } from "../api/guest";

type Health = { status: string; version: string; ruleCatalogSize: number };

/** Chỉ cho phép quay về đường dẫn nội bộ (tránh open redirect qua ?next=). */
export function safeNext(next: string | null): string {
  return next && /^\/(?!\/)/.test(next) ? next : "/lobby";
}

export function HomePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const me = useQuery({ queryKey: ["guest", "me"], queryFn: guestApi.me });
  const [nickname, setNickname] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => (res.ok ? (res.json() as Promise<Health>) : Promise.reject(new Error(String(res.status)))))
      .then(setHealth)
      .catch(() => setHealthError(true));
  }, []);

  const create = useMutation({
    mutationFn: () => guestApi.create(nickname),
    onSuccess: (profile) => {
      queryClient.setQueryData(["guest", "me"], profile);
      navigate(next);
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <main className="app home">
      <header className="brand">
        <span className="brand-mark" aria-hidden="true">
          ♠
        </span>
        <h1>
          Lớp học <span className="accent-text">Thầy Trung</span>
        </h1>
        <p className="muted">Chơi 4 người với bạn bè. Không dùng tiền thật.</p>
      </header>

      {me.data ? (
        <section className="panel welcome">
          <p className="eyebrow">Xin chào</p>
          <p className="welcome-name">
            <strong>{me.data.nickname}</strong>
          </p>
          <div className="actions">
            {me.data.currentRoom ? (
              <button className="primary lg" onClick={() => navigate(`/r/${me.data!.currentRoom!.code}`)}>
                Quay lại phòng {me.data.currentRoom.code}
              </button>
            ) : (
              <button className="primary lg" onClick={() => navigate(next)}>
                Vào sảnh
              </button>
            )}
          </div>
        </section>
      ) : (
        !me.isLoading && (
          <form className="panel form" onSubmit={submit}>
            <label htmlFor="nickname">Tên hiển thị của bạn</label>
            <input
              id="nickname"
              value={nickname}
              maxLength={20}
              autoComplete="nickname"
              placeholder="Ví dụ: Minh Anh"
              onChange={(e) => setNickname(e.target.value)}
              required
            />
            {create.error && (
              <p role="alert" className="error">
                {errorMessage(create.error)}
              </p>
            )}
            <button type="submit" className="primary lg" disabled={create.isPending || nickname.trim().length < 2}>
              Vào chơi
            </button>
          </form>
        )
      )}

      <footer className="home-foot">
        <p className={`status small ${health ? "up" : healthError ? "down" : ""}`}>
          <span className="dot" aria-hidden="true" />
          {health && `Máy chủ hoạt động · phiên bản ${health.version} · ${health.ruleCatalogSize} luật`}
          {!health && !healthError && "Đang kết nối máy chủ…"}
        </p>
        {healthError && <p role="alert">Không kết nối được máy chủ.</p>}
        <p>
          <Link to="/rules">Xem luật đang áp dụng</Link>
        </p>
      </footer>
    </main>
  );
}
