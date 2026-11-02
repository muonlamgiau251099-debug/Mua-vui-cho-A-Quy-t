import { Link } from "react-router-dom";
import { RulesView } from "./RulesView";

// Trang xem luật cho người chơi (từ trang chủ). Trong phòng, luật mở thành popup (xem RulesView) để không rời phòng.
export function RulesPage() {
  return (
    <main className="app wide">
      <p>
        <Link to="/">← Trang chủ</Link>
      </p>
      <h1>Luật đang áp dụng</h1>
      <RulesView />
    </main>
  );
}
