// Dữ liệu ván do server gửi (tlmn_engine/projection.py). Client chỉ hiển thị, không tự tính luật.

export type PlayerView = {
  seat: number;
  cardCount: number;
  playedCount: number;
  status: "ACTIVE" | "FINISHED" | "CONG" | "FORFEITED";
  rank: number | null;
};

export type Transfer = { from: number; to: number; amount: number; reason: string; detail: Record<string, unknown> };

export type GameView = {
  phase: "PLAYING" | "FINISHED" | "CANCELLED";
  openingMode: "THREE_CLUBS" | "WINNER_LEADS";
  current: number | null;
  turnDeadline: number | null; // epoch giây (giờ server)
  firstMovePending: boolean;
  openingCard?: number; // lá người đánh đầu phải có (mặc định 3♣; lá khác khi 3♣ không được chia)
  trick: {
    leader: number;
    top: number[] | null;
    topCombo: string | null;
    topSeat: number | null;
    topIsChop: boolean;
    passed: number[];
    chainValue: number;
  };
  players: PlayerView[];
  finishOrder: number[];
  endType: string | null;
  transfers: Transfer[];
  net: number[];
  hands?: number[][];
  yourSeat?: number | null;
  yourHand?: number[] | null;
};

export type GameEvent = { type: string; [key: string]: unknown };

export type GameHeader = {
  gameId: string;
  rules: { version: number; hash: string };
  deckCommitment: string;
};

export type LiveGame = GameHeader & { sequence: number; state: GameView; events: GameEvent[] };

export type GameResult = GameHeader & {
  result: GameView;
  deckReveal: { deck: number[]; salt: string } | null;
};
