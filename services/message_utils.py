from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import config, get_logger
import logging

logger = get_logger()
bot = Bot(token=config.BOT_TOKEN, parse_mode="Markdown")


async def send_incident_notification(event_id: str, subject: str, message: str) -> int:
    """Отправка уведомления об инциденте в Telegram"""
    try:
        text = f"*{subject}*\n{message}\nEvent ID: `{event_id}`"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Взять в работу", callback_data=f"take:{event_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Отклонить", callback_data=f"reject:{event_id}"
                    )
                ],
            ]
        )

        result = await bot.send_message(
            chat_id=config.GROUP_ID,
            message_thread_id=config.TOPIC_ID,
            text=text,
            reply_markup=keyboard,
        )

        logger.info(f"Уведомление отправлено для event_id: {event_id}")
        return result.message_id
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {str(e)}")
        return None


async def edit_message_text(
    chat_id: int, message_id: int, text: str, reply_markup=None
):
    """Редактирование существующего сообщения"""
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup
        )
        get_logger.debug(f"Сообщение {message_id} обновлено")
    except Exception as e:
        get_logger.error(f"Ошибка редактирования сообщения: {str(e)}")
