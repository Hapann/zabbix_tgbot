from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import config
from database.models import Incident, IncidentStatus

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
    return result.message_id

async def update_incident_message(incident: Incident, buttons=None, remove_buttons=False):
    status_text = {
        IncidentStatus.open: "������ Открыт",
        IncidentStatus.in_progress: "������ В работе",
        IncidentStatus.closed: "������ Закрыт",
        IncidentStatus.rejected: "⚪ Отклонен"
    }
    
    text = f"{incident.original_text}\n\n"
    text += f"*Статус:* {status_text[incident.status]}\n"
    
    if incident.assigned_to:
        text += f"*Исполнитель:* {incident.assigned_to}\n"
    
    if incident.resolution_comment:
        text += f"*Комментарий:* {incident.resolution_comment}"
    
    reply_markup = None
    if buttons:
        reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    elif not remove_buttons:
        # Default buttons for in_progress state
        if incident.status == IncidentStatus.in_progress:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Закрыть", callback_data=f"close:{incident.event_id}")],
                [InlineKeyboardButton(text="Отклонить", callback_data=f"reject:{incident.event_id}")]
            ])
    
    await bot.edit_message_text(
        chat_id=incident.chat_id,
        message_id=incident.message_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )