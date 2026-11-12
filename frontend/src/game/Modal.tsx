import { useEffect, type ReactNode } from "react";

type Props = { title: string; onClose: () => void; wide?: boolean; children: ReactNode };

/**
 * Popup: đóng bằng nút X, bấm ra ngoài hoặc phím Esc. Tiêu đề cố định, nội dung cuộn bên trong để không bao giờ
 * bị cắt khi màn hình thấp (điện thoại xoay ngang).
 */
export function Modal({ title, onClose, wide, children }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className={`dialog modal${wide ? " wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="modal-close" aria-label="Đóng" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
