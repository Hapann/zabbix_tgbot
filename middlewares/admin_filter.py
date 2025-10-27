from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Any, Dict, Awaitable
from globals.config import ADMIN_IDS


class AdminAccessMiddleware(BaseMiddleware):
    """Пропускает только указанных пользователей, остальных игнорирует молча."""

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = (
            event.from_user.id
            if hasattr(event, "from_user") and event.from_user
            else None
        )

        # Если пользователь не из списка админов — просто выходим (игнор)
        if user_id not in ADMIN_IDS:
            return  # пропускаем без ответа, бот не реагирует

        return await handler(event, data)