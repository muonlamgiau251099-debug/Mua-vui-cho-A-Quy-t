import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { rulesApi } from "../api/rules";

export function AdminLayout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["admin", "me"], queryFn: rulesApi.me, retry: false });
  const logout = useMutation({
    mutationFn: rulesApi.logout,
    onSettled: () => {
      queryClient.removeQueries({ queryKey: ["admin"] });
      navigate("/admin/login");
    },
  });

  if (me.isLoading) return <p className="app">Đang kiểm tra đăng nhập…</p>;
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/admin/login" replace />;
  if (me.error) return <p className="app" role="alert">Không kết nối được máy chủ.</p>;

  return (
    <div className="admin">
      <header className="admin-bar">
        <strong>Quản trị · Lớp học Thầy Trung</strong>
        <nav>
          <NavLink to="/admin/rules">Luật</NavLink>
          <NavLink to="/admin/versions">Phiên bản</NavLink>
          <NavLink to="/admin/audit">Nhật ký</NavLink>
          <NavLink to="/admin/games">Đối soát ván</NavLink>
        </nav>
        <span className="admin-user">
          {me.data!.admin.username}{" "}
          <button onClick={() => logout.mutate()} disabled={logout.isPending}>
            Đăng xuất
          </button>
        </span>
      </header>
      <main className="app wide">
        <Outlet />
      </main>
    </div>
  );
}
