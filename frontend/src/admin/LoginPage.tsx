import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { errorMessage } from "../api/client";
import { rulesApi } from "../api/rules";

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => rulesApi.login(username, password),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
      navigate("/admin/rules");
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };

  return (
    <main className="app narrow">
      <h1>Đăng nhập Admin</h1>
      <form onSubmit={submit} className="form">
        <label htmlFor="username">Tên đăng nhập</label>
        <input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <label htmlFor="password">Mật khẩu</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {login.error && <p role="alert" className="error">{errorMessage(login.error)}</p>}
        <button type="submit" className="primary" disabled={login.isPending}>
          Đăng nhập
        </button>
      </form>
    </main>
  );
}
