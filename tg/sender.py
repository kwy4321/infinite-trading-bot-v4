"""Telegram outbound messages — isolated from trading logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from state.runtime_settings import RuntimeSettings

logger = logging.getLogger(__name__)


class TelegramSender:
    def __init__(
        self,
        bot,
        chat_ids: Sequence[int],
        *,
        runtime: "RuntimeSettings | None" = None,
    ):
        self._bot = bot
        self._chat_ids = list(chat_ids)
        self._runtime = runtime

    def set_bot(self, bot) -> None:
        self._bot = bot

    def _effective_chat_ids(self) -> list[int]:
        if self._chat_ids:
            return list(self._chat_ids)
        if self._runtime:
            return self._runtime.notify_chat_ids()
        return []

    async def send_to(
        self, chat_id: int, text: str, parse_mode: Optional[str] = None,
    ) -> None:
        if not self._bot:
            logger.info("Telegram (no bot): %s", text[:120])
            return
        try:
            await self._bot.send_message(chat_id, text, parse_mode=parse_mode)
        except Exception:
            logger.exception("Failed to send telegram to %s", chat_id)

    async def send(self, text: str, parse_mode: Optional[str] = None) -> None:
        chat_ids = self._effective_chat_ids()
        if not self._bot or not chat_ids:
            logger.warning(
                "Telegram send skipped — chat_id 없음 "
                "(.env TELEGRAM_ALLOWED_CHAT_IDS 또는 CHAT_ID 설정)"
            )
            logger.info("Telegram (no chat): %s", text[:120])
            return
        for chat_id in chat_ids:
            await self.send_to(chat_id, text, parse_mode=parse_mode)
