import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ApiError, errorMessage } from "../api/client";
import { guestApi, roomApi, tokenStore } from "../api/guest";
import { COMPACT_QUERY, useMediaQuery } from "../lib/useMediaQuery";
import { useRoomSocket } from "../realtime/useRoomSocket";
import { GameResultPanel } from "../game/GameResultPanel";
import { GameTable } from "../game/GameTable";
import { RankBanner } from "../game/RankBanner";
import { SessionScoreboard } from "../room/SessionScoreboard";
import { WaitingRoom } from "../room/WaitingRoom";

export function RoomPage() {
  const { code = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["guest", "me"], queryFn: guestApi.me });
  const preview = useQuery({ queryKey: ["room", code], queryFn: () => roomApi.byCode(code), retry: false });
  const [joinError, setJoinError] = useState<string | null>(null);
  const compact = useMediaQuery(COMPACT_QUERY);

  const roomId = preview.data?.roomId ?? null;
  const seatedHere = !!me.data?.currentRoom && me.data.currentRoom.roomId === roomId;
  const seatedElsewhere = !!me.data?.currentRoom && !seatedHere;

  // Chưa ngồi ở phòng nào → tự vào ghế trống đầu tiên.
  const join = useMutation({
    mutationFn: () => roomApi.join(roomId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["guest", "me"] }),
    onError: (e) => setJoinError(errorMessage(e)),
  });
  const shouldJoin = !!roomId && !!me.data && !me.data.currentRoom && !join.isPending && !join.isSuccess && !joinError;
  useEffect(() => {
    if (shouldJoin) join.mutate();
  }, [shouldJoin, join]);

  const socket = useRoomSocket(seatedHere ? roomId : null, seatedHere ? tokenStore.get() : null);

  const leaveToLobby = async (action: (id: string) => Promise<void>) => {
    try {
      await action(roomId!);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) {
        setJoinError(errorMessage(e));
        return;
      }
    }
    await queryClient.invalidateQueries({ queryKey: ["guest", "me"] });
    navigate("/lobby");
  };

  if (me.isLoading || preview.isLoading) return <main className="app">Đang tải phòng…</main>;
  if (!me.data) return <Navigate to={`/?next=/r/${code}`} replace />;
  if (preview.error)
    return (
      <main className="app narrow">
        <p role="alert">
          {preview.error instanceof ApiError && preview.error.status === 404
            ? `Không tìm thấy phòng ${code} hoặc phòng đã đóng.`
            : errorMessage(preview.error)}
        </p>
        <Link to="/lobby">Về sảnh</Link>
      </main>
    );
  if (seatedElsewhere)
    return (
      <main className="app narrow">
        <p>Bạn đang ngồi ở phòng {me.data.currentRoom!.code}. Hãy rời phòng đó trước.</p>
        <Link to={`/r/${me.data.currentRoom!.code}`}>Về phòng của bạn</Link>
      </main>
    );
  if (joinError && !seatedHere)
    return (
      <main className="app narrow">
        <p role="alert">{joinError}</p>
        <Link to="/lobby">Về sảnh</Link>
      </main>
    );
  if (socket.finalMessage)
    return (
      <main className="app narrow">
        <p role="alert">{socket.finalMessage}</p>
        <Link to="/lobby" onClick={() => void queryClient.invalidateQueries({ queryKey: ["guest", "me"] })}>
          Về sảnh
        </Link>
      </main>
    );

  const room = socket.room ?? preview.data!;
  const inviteUrl = `${window.location.origin}/r/${room.code}`;
  const yourSeat = socket.room?.yourSeat ?? me.data.currentRoom?.seatNo ?? null;

  // Điện thoại đang chơi: bàn chiếm trọn màn hình; điểm phiên nằm trong popup "Thông tin", nút "Rời phòng" nằm trên bàn.
  const tableMode = compact;

  return (
    <main className={`app${tableMode ? " table-mode" : ""}`}>
      {socket.status !== "open" && (
        <div className="banner" role="status">
          {socket.status === "reconnecting" ? "Mất kết nối, đang kết nối lại…" : "Đang kết nối…"}
        </div>
      )}
      {socket.notice && (
        <div className="message" role="status" onClick={socket.clearNotice}>
          {socket.notice}
        </div>
      )}
      {!tableMode && <SessionScoreboard session={room.session} yourSeat={yourSeat} />}
      {socket.game ? (
        <>
          <GameTable
            game={socket.game}
            seats={room.seats}
            canAct={socket.status === "open"}
            error={socket.lastError}
            clockOffset={socket.clockOffset}
            chats={socket.chats}
            info={<SessionScoreboard session={room.session} yourSeat={yourSeat} />}
            onLeave={() => void leaveToLobby(roomApi.leave)}
            onChat={(msg) => socket.send("chat.send", msg)}
            onPlay={(cards) => socket.send("game.play", { cards })}
            onPass={() => socket.send("game.pass")}
          />
          {!tableMode && (
            <div className="actions">
              <button
                type="button"
                className="danger"
                onClick={() =>
                  window.confirm("Rời phòng khi đang chơi sẽ bị xử thua (xếp bét). Vẫn rời?") &&
                  void leaveToLobby(roomApi.leave)
                }
              >
                Rời phòng
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          {socket.lastError && <p className="error">{socket.lastError}</p>}
          {joinError && seatedHere && (
            <p role="alert" className="error">
              {joinError}
            </p>
          )}
          <WaitingRoom
            room={room}
            yourSeat={yourSeat}
            canAct={socket.status === "open"}
            inviteUrl={inviteUrl}
            info={<SessionScoreboard session={room.session} yourSeat={yourSeat} />}
            onReady={(ready) => socket.send("room.ready", { ready })}
            onLeave={() => void leaveToLobby(roomApi.leave)}
            onClose={() =>
              window.confirm("Đóng phòng? Mọi người sẽ bị đưa ra sảnh.") && void leaveToLobby(roomApi.close)
            }
            onKick={(seat) => {
              if (window.confirm(`Mời ${seat.nickname ?? "người chơi"} ra khỏi phòng?`)) {
                roomApi.kick(room.roomId, seat.seatNo).catch((e: unknown) => setJoinError(errorMessage(e)));
              }
            }}
            onRestartSession={() => {
              if (window.confirm("Bắt đầu phiên mới? Điểm của mọi người sẽ về 0 (lịch sử phiên cũ vẫn được lưu).")) {
                roomApi.restartSession(room.roomId).catch((e: unknown) => setJoinError(errorMessage(e)));
              }
            }}
            onChangePlayerCount={(count) => {
              roomApi.setPlayerCount(room.roomId, count).catch((e: unknown) => setJoinError(errorMessage(e)));
            }}
          />
        </>
      )}
      {socket.result && (
        <GameResultPanel
          result={socket.result}
          seats={room.seats}
          yourSeat={yourSeat}
          onClose={socket.clearResult}
          onReady={() => {
            socket.send("room.ready", { ready: true });
            socket.clearResult();
          }}
        />
      )}
      <RankBanner game={socket.game} result={socket.result} seats={room.seats} />
    </main>
  );
}
