# services/message_utils.py
from aiogram import Bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import config
from database import db

bot = Bot(token=config.BOT_TOKEN)

async def send_incident_notification(event_id: str, subject: str, message: str) -> int:
    text = f"*{subject}*\n{message}\nEvent ID: `{event_id}`"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Взять в работу", callback_data=f"take:{event_id}")],
        [InlineKeyboardButton(text="Отклонить", callback_data=f"reject:{event_id}")]
    ])
    
    result = await bot.send_message(
        chat_id=config.GROUP_ID,
        message_thread_id=config.TOPIC_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    # Сохраняем инцидент в БД
    await db.execute(
        "INSERT INTO incidents (event_id, message_id, chat_id, thread_id, status, original_text) "
        "VALUES ($1, $2, $3, $4, 'open', $5) "
        "ON CONFLICT (event_id) DO NOTHING",
        event_id, result.message_id, config.GROUP_ID, config.TOPIC_ID, text
    )
    
    return result.message_id