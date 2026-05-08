from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from services.repositories import ConfirmationRepository, GameRepository, PlayerRepository
from services.telegram_service import TelegramService
from utils.formatting import RenderInput, render_game_message


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameContext:
    game_id: int
    chat_id: int
    message_id: int
    game_date: date
    status: str
    max_players: int


class GameService:
    def __init__(self, conn: sqlite3.Connection, telegram: TelegramService) -> None:
        self._conn = conn
        self._telegram = telegram
        self._games = GameRepository(conn)
        self._players = PlayerRepository(conn)
        self._confirmations = ConfirmationRepository(conn)

    def get_open_game(self, chat_id: int):
        return self._games.get_open(chat_id)

    async def create_or_refresh_list(
        self,
        *,
        chat_id: int,
        game_date: date,
        max_players: int,
        game_name: str,
        game_day: str,
        game_time: str,
        game_location: str,
        game_address: str,
    ) -> GameContext:
        current = self._games.get_open(chat_id)
        if current is None:
            previous = self._games.get_current(chat_id)
            game_id = self._games.create(chat_id, game_date, max_players)
            message_text = self._render_message(
                game_id=game_id,
                game_name=game_name,
                game_day=game_day,
                game_time=game_time,
                game_location=game_location,
                game_address=game_address,
                game_date=game_date,
                status="open",
                max_players=max_players,
            )
            msg = await self._telegram.send_list_message(chat_id, message_text, reply_markup=self._keyboard(open_=True))
            self._games.set_message_id(game_id, msg.message_id)

            # unpin anterior (se houver)
            if previous and previous.message_id:
                try:
                    await self._telegram.unpin_message(chat_id, int(previous.message_id))
                except Exception:
                    logger.info("Falha ao desafixar lista antiga (ignorado).")

            await self._telegram.pin_message(chat_id, msg.message_id)
            return GameContext(
                game_id=game_id,
                chat_id=chat_id,
                message_id=msg.message_id,
                game_date=game_date,
                status="open",
                max_players=max_players,
            )

        # já existe lista aberta -> re-render e re-fixa (sem spam)
        assert current.message_id is not None
        message_text = self._render_message(
            game_id=current.id,
            game_name=game_name,
            game_day=game_day,
            game_time=game_time,
            game_location=game_location,
            game_address=game_address,
            game_date=date.fromisoformat(current.game_date),
            status=current.status,
            max_players=current.max_players,
        )
        try:
            await self._telegram.edit_list_message(
                chat_id,
                int(current.message_id),
                message_text,
                reply_markup=self._keyboard(open_=True),
            )
            await self._telegram.pin_message(chat_id, int(current.message_id))
        except BadRequest as e:
            # Ex.: "Message to edit not found" quando a mensagem foi deletada manualmente.
            # Recria a mensagem, atualiza o message_id e fixa novamente.
            msg_text = str(e)
            if "Message to edit not found" not in msg_text:
                raise
            msg = await self._telegram.send_list_message(
                chat_id,
                message_text,
                reply_markup=self._keyboard(open_=True),
            )
            self._games.set_message_id(current.id, msg.message_id)
            await self._telegram.pin_message(chat_id, msg.message_id)
        return GameContext(
            game_id=current.id,
            chat_id=current.chat_id,
            message_id=msg.message_id if "msg" in locals() else int(current.message_id),
            game_date=date.fromisoformat(current.game_date),
            status=current.status,
            max_players=current.max_players,
        )

    async def close_list(
        self,
        *,
        chat_id: int,
        game_name: str,
        game_day: str,
        game_time: str,
        game_location: str,
        game_address: str,
    ) -> GameContext | None:
        game = self._games.get_open(chat_id)
        if game is None or game.message_id is None:
            return None
        self._games.set_status(game.id, "closed")

        message_text = self._render_message(
            game_id=game.id,
            game_name=game_name,
            game_day=game_day,
            game_time=game_time,
            game_location=game_location,
            game_address=game_address,
            game_date=date.fromisoformat(game.game_date),
            status="closed",
            max_players=game.max_players,
        )
        await self._telegram.edit_list_message(chat_id, int(game.message_id), message_text, reply_markup=self._keyboard(open_=False))
        return GameContext(
            game_id=game.id,
            chat_id=game.chat_id,
            message_id=int(game.message_id),
            game_date=date.fromisoformat(game.game_date),
            status="closed",
            max_players=game.max_players,
        )

    async def reset_list(
        self,
        *,
        chat_id: int,
        game_name: str,
        game_day: str,
        game_time: str,
        game_location: str,
        game_address: str,
    ) -> bool:
        game = self._games.get_current(chat_id)
        if game is None or game.message_id is None:
            return False
        self._confirmations.reset_game(game.id)
        message_text = self._render_message(
            game_id=game.id,
            game_name=game_name,
            game_day=game_day,
            game_time=game_time,
            game_location=game_location,
            game_address=game_address,
            game_date=date.fromisoformat(game.game_date),
            status=game.status,
            max_players=game.max_players,
        )
        await self._telegram.edit_list_message(
            chat_id,
            int(game.message_id),
            message_text,
            reply_markup=self._keyboard(open_=(game.status == "open")),
        )
        return True

    async def delete_current_list(self, *, chat_id: int) -> bool:
        """
        Apaga a lista/jogo atual do chat:
        - tenta desafixar e deletar a mensagem do bot (se existir)
        - apaga o registro em `games` (cascade remove confirmações)
        """
        game = self._games.get_current(chat_id)
        if game is None:
            return False

        if game.message_id:
            try:
                await self._telegram.unpin_message(chat_id, int(game.message_id))
            except Exception:
                logger.info("Falha ao desafixar mensagem (ignorado).")
            try:
                await self._telegram.delete_message(chat_id, int(game.message_id))
            except Exception:
                logger.info("Falha ao deletar mensagem (ignorado).")

        self._games.delete(game.id)
        return True

    async def refresh_message(
        self,
        *,
        chat_id: int,
        message_id: int,
        game_id: int,
        game_status: str,
        max_players: int,
        game_name: str,
        game_day: str,
        game_time: str,
        game_location: str,
        game_address: str,
        game_date: date,
    ) -> None:
        text = self._render_message(
            game_id=game_id,
            game_name=game_name,
            game_day=game_day,
            game_time=game_time,
            game_location=game_location,
            game_address=game_address,
            game_date=game_date,
            status=game_status,
            max_players=max_players,
        )
        await self._telegram.edit_list_message(chat_id, message_id, text, reply_markup=self._keyboard(open_=(game_status == "open")))

    def _keyboard(self, *, open_: bool) -> InlineKeyboardMarkup | None:
        if not open_:
            return None
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Vou jogar", callback_data="list:vou")],
                [InlineKeyboardButton("❌ Não vou", callback_data="list:nao_vou")],
            ]
        )

    def _render_message(
        self,
        *,
        game_id: int,
        game_name: str,
        game_day: str,
        game_time: str,
        game_location: str,
        game_address: str,
        game_date: date,
        status: str,
        max_players: int,
    ) -> str:
        confirmed_ids = self._confirmations.list_by_status(game_id, "vou")
        waiting_ids = self._confirmations.list_by_status(game_id, "espera")
        not_going_ids = self._confirmations.list_by_status(game_id, "nao_vou")

        confirmed = [self._players.get_display_name(pid) for pid in confirmed_ids]
        waiting = [self._players.get_display_name(pid) for pid in waiting_ids]
        not_going = [self._players.get_display_name(pid) for pid in not_going_ids]

        return render_game_message(
            RenderInput(
                game_name=game_name,
                game_day=game_day,
                game_time=game_time,
                game_location=game_location,
                game_address=game_address,
                game_date=game_date,
                status=status,
                max_players=max_players,
                confirmed=confirmed,
                not_going=not_going,
                waiting=waiting,
            )
        )

