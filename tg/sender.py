"""Telegram outbound messages — isolated from trading logic."""

import logging
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


class TelegramSender:
    def __init__(self, bot, chat_ids: Sequence[int]):
        self._bot = bot
        self._chat_ids = list(chat_ids)

    def set_bot(self, bot) -> None:
        self._bot = bot

    async def send(self, text: str, parse_mode: Optional[str] = None) -> None:
        if not self._bot or not self._chat_ids:
            logger.info("Telegram (no chat): %s", text[:120])
            return
        for chat_id in self._chat_ids:
            try:
                await self._bot.send_message(chat_id, text, parse_mode=parse_mode)
            except Exception:
                logger.exception("Failed to send telegram to %s", chat_id)
