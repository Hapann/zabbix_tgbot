from aiogram import Bot
from config import config

# Создаем глобальный экземпляр бота
bot = Bot(token=config.BOT_TOKEN, parse_mode="Markdown")


async def edit_message_text(
    chat_id: int, message_id: int, text: str, reply_markup=None
):
    """Универсальная функция для редактирования сообщений"""
    await bot.edit_message_text(
        chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup
    )
