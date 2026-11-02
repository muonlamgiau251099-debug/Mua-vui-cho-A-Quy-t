import type { GameView } from "../game/types";
import { ApiError, api } from "./client";

// Token reconnect của khách: lưu ở localStorage của trình duyệt này (có thể bị chặn → dùng bộ nhớ tạm).
const TOKEN_KEY = "tlmn_guest_token";
let memoryToken: string | null = null;

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY) ?? memoryToken;
    } catch {
      return memoryToken;
    }
  },
  set(token: string | null): void {
    memoryToken = token;
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* localStorage bị chặn: chỉ giữ trong bộ nhớ */
    }
  },
};

export type CurrentRoom = { roomId: string; code: string; seatNo: number };
export type GuestProfile = { guestId: string; nickname: string; currentRoom: CurrentRoom | null };

export type SeatState = {
  seatNo: number;
  occupied: boolean;
  nickname: string | null;
  ready: boolean;
  connected: boolean;
  holdUntil: string | null;
};

export type RoomState = {
  roomId: string;
  code: string;
  status: "WAITING" | "PLAYING" | "CLOSED";
  version: number;
  ownerSeat: number | null;
  seats: SeatState[];
  allReady: boolean;
  rules: { version: number; configHash: string } | null;
  gameId?: string | null;
  session?: SessionSummary | null;
  yourSeat?: number;
};

export type SessionSummary = {
  sessionId: string;
  sessionNo: number;
  gamesPlayed: number;
  scores: { seat: number; nickname: string | null; total: number }[];
};

export type Standing = { seat: number; nickname: string | null; total: number; gamesCounted: number; place: number };

export type SessionListItem = {
  sessionId: string;
  roomCode: string;
  sessionNo: number;
  status: "ACTIVE" | "ENDED";
  startedAt: string;
  endedAt: string | null;
  gamesPlayed: number;
  standings: Standing[];
};

export type SessionGame = {
  gameId: string;
  gameNo: number;
  status: "IN_PROGRESS" | "FINISHED" | "CANCELLED";
  endType: string | null;
  cancelReason: string | null;
  ruleVersion: number;
  startedAt: string;
  endedAt: string | null;
  ranks: (number | null)[] | null;
  net: number[] | null;
  cumulative: number[] | null;
  transfers: { from: number; to: number; amount: number; reason: string }[];
};

export type SessionDetail = Omit<SessionListItem, "gamesPlayed"> & {
  endReason: string | null;
  players: { seat: number; nickname: string | null }[];
  games: SessionGame[];
};

function auth(): Record<string, string> {
  const token = tokenStore.get();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export const guestApi = {
  async create(nickname: string): Promise<GuestProfile> {
    const body = await api<GuestProfile & { token: string }>("/api/guests", { method: "POST", body: { nickname } });
    tokenStore.set(body.token);
    return body;
  },
  async me(): Promise<GuestProfile | null> {
    if (!tokenStore.get()) return null;
    try {
      return await api<GuestProfile>("/api/guests/me", { headers: auth() });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        tokenStore.set(null);
        return null;
      }
      throw e;
    }
  },
  rename: (nickname: string) => api<GuestProfile>("/api/guests/me", { method: "PATCH", body: { nickname }, headers: auth() }),
};

export const roomApi = {
  create: () => api<{ roomId: string; code: string; invitePath: string }>("/api/rooms", { method: "POST", headers: auth() }),
  byCode: (code: string) => api<RoomState>(`/api/rooms/by-code/${encodeURIComponent(code)}`),
  join: (roomId: string, seatNo?: number) =>
    api<{ roomId: string; seatNo: number }>(`/api/rooms/${roomId}/join`, {
      method: "POST",
      body: seatNo === undefined ? {} : { seatNo },
      headers: auth(),
    }),
  leave: (roomId: string) => api<void>(`/api/rooms/${roomId}/leave`, { method: "POST", headers: auth() }),
  close: (roomId: string) => api<void>(`/api/rooms/${roomId}/close`, { method: "POST", headers: auth() }),
  restartSession: (roomId: string) =>
    api<void>(`/api/rooms/${roomId}/sessions/restart`, { method: "POST", headers: auth() }),
};

export type ReplayStep = {
  seq: number;
  kind: string;
  seat: number | null;
  events: { type: string; [key: string]: unknown }[];
  view: GameView & { hands: number[][] };
};

export type GameReplay = {
  gameId: string;
  gameNo: number;
  sessionId: string;
  roomCode: string;
  status: string;
  endType: string | null;
  ruleVersion: number;
  deckCommitment: string;
  deckSalt: string;
  verified: boolean;
  players: { seat: number; nickname: string | null }[];
  initial: GameView & { hands: number[][] };
  steps: ReplayStep[];
};

export const historyApi = {
  replay: (gameId: string) => api<GameReplay>(`/api/games/${gameId}/replay`, { headers: auth() }),
  mySessions: () => api<{ items: SessionListItem[] }>("/api/guests/me/sessions", { headers: auth() }),
  session: (sessionId: string) => api<SessionDetail>(`/api/sessions/${sessionId}`, { headers: auth() }),
};
