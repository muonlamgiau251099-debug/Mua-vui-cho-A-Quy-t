import avatar1 from "../assets/avatars/avatar-1.jpg";
import avatar2 from "../assets/avatars/avatar-2.jpg";
import avatar3 from "../assets/avatars/avatar-3.jpg";
import avatar4 from "../assets/avatars/avatar-4.jpg";

const AVATARS = [avatar1, avatar2, avatar3, avatar4];

/** Ảnh đại diện cố định theo số ghế (ghế 1 → ảnh 1, …, ghế 4 → ảnh 4). */
export function avatarFor(seatNo: number): string {
  return AVATARS[((seatNo % AVATARS.length) + AVATARS.length) % AVATARS.length]!;
}
