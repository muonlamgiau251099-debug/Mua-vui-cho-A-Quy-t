import { useEffect, useState } from "react";

const supported = () => typeof window !== "undefined" && typeof window.matchMedia === "function";

/** true khi media query khớp (vd "(max-width: 600px)"); cập nhật khi xoay màn hình / đổi kích thước. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => supported() && window.matchMedia(query).matches);
  useEffect(() => {
    if (!supported()) return;
    const mq = window.matchMedia(query);
    const update = () => setMatches(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [query]);
  return matches;
}

/** Điện thoại: màn hẹp (dọc) hoặc màn thấp (xoay ngang). Bàn chơi chuyển sang bố cục gọn trong một bàn. */
export const COMPACT_QUERY = "(max-width: 600px), (max-height: 500px)";
