"""Tác vụ nền: nhả các ghế mất kết nối quá thời gian giữ ghế (ID 144) rồi broadcast."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.realtime.games import GameManager
from app.realtime.hub import RoomHub
from app.services import rooms

log = logging.getLogger(__name__)


async def sweep_once(
    sessionmaker: async_sessionmaker[AsyncSession],
    hub: RoomHub,
    now: datetime | None = None,
    games: GameManager | None = None,
) -> rooms.SweepResult:
    async with sessionmaker() as session:
        result = await rooms.sweep_expired_holds(session, now)
    if games is not None:
        for room_id, guest_id in result.expired_in_game:  # D9, R6: mất kết nối quá hạn khi đang chơi
            await games.forfeit(room_id, guest_id)
    for room_id in result.changed_rooms:
        if room_id in result.closed_rooms:
            await hub.close_room(room_id, "EMPTY")
        else:
            await hub.broadcast_state(room_id)
    return result


async def run_sweeper(
    sessionmaker: async_sessionmaker[AsyncSession], hub: RoomHub, interval: float, games: GameManager
) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await sweep_once(sessionmaker, hub, games=games)
        except (SQLAlchemyError, OSError):
            log.exception("Sweeper lỗi; sẽ thử lại ở vòng sau")
