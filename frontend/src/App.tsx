import { Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./admin/AdminLayout";
import { AuditPage } from "./admin/AuditPage";
import { GameAuditPage } from "./admin/GameAuditPage";
import { LoginPage } from "./admin/LoginPage";
import { RulesDashboard } from "./admin/RulesDashboard";
import { VersionsPage } from "./admin/VersionsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { HomePage } from "./pages/HomePage";
import { LobbyPage } from "./pages/LobbyPage";
import { ReplayPage } from "./pages/ReplayPage";
import { RoomPage } from "./pages/RoomPage";
import { RulesPage } from "./pages/RulesPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/lobby" element={<LobbyPage />} />
      <Route path="/r/:code" element={<RoomPage />} />
      <Route path="/rules" element={<RulesPage />} />
      <Route path="/history/:sessionId" element={<HistoryPage />} />
      <Route path="/replay/:gameId" element={<ReplayPage />} />
      <Route path="/admin/login" element={<LoginPage />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Navigate to="rules" replace />} />
        <Route path="rules" element={<RulesDashboard />} />
        <Route path="versions" element={<VersionsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="games" element={<GameAuditPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
