from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database
from globals import GROUP_ID, TOPIC_ID
from logger.logger import logger

router = Router()

def log_command(message: Message, command: str):
    """Логирование вызова команды"""
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    logger.info(f"Пользователь {user_id} ({username}) - Успешно вызвана команда {command}")

# Кнопки для инцидента
def incident_buttons(incident_id: int, status: str):
    if status == "new":
        buttons = [
            [InlineKeyboardButton(text="В работу", callback_data=f"take_{incident_id}"),
             InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{incident_id}")]
        ]
    elif status == "in_progress":
        buttons = [
            [InlineKeyboardButton(text="Закрыть", callback_data=f"close_{incident_id}")]
        ]
    else:
        buttons = []
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command(commands=["help"]))
async def help_handler(message: Message):
    log_command(message, "/help")
    await message.answer(
        "Этот бот принимает алерты из Zabbix и позволяет управлять инцидентами.\n"
        "Команды:\n"
        "/help - помощь\n"
        "/rules - инструкция по работе с ботом\n"
        "/stats - статистика по инцидентам"
    )

@router.message(Command(commands=["rules"]))
async def rules_handler(message: Message):
    log_command(message, "/rules")
    await message.answer(
        "Правила работы с ботом:\n"
        "1. При получении алерта вы можете взять инцидент в работу или отклонить.\n"
        "2. При взятии в работу необходимо будет оставить комментарий при закрытии.\n"
        "3. При отклонении также требуется комментарий.\n"
        "4. Все действия фиксируются в базе."
    )

@router.message(Command(commands=["stats"]))
async def stats_handler(message: Message, db: Database):
    log_command(message, "/stats")
    try:
        stats = await db.get_incident_stats()
        response = (
            "📊 Статистика инцидентов:\n"
            f"• Всего инцидентов: {stats['total']}\n"
            f"• В работе: {stats['in_progress']}\n"
            f"• Закрыто: {stats['closed']}\n"
            f"• Отклонено: {stats['rejected']}"
        )
        await message.answer(response)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("Произошла ошибка при получении статистики.")

async def send_incident_to_group(bot, incident_id: int, event: str, node: str, 
                               trigger: str, status: str, severity: str, details: str):
    text = (
        f"🚨 <b>Новый инцидент #{incident_id}</b>\n"
        f"<b>Событие:</b> {event}\n"
        f"<b>На узле:</b> {node}\n"
        f"<b>Триггер:</b> {trigger}\n"
        f"<b>Состояние:</b> {status}\n"
        f"<b>Уровень критичности:</b> {severity}\n"
        f"<b>Подробности:</b> {details}\n"
        f"<b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    keyboard = incident_buttons(incident_id, "new")
    
    try:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=text,
            reply_markup=keyboard,
            message_thread_id=TOPIC_ID,
            parse_mode="HTML"
        )
        logger.info(f"Инцидент #{incident_id} отправлен в группу")
    except Exception as e:
        logger.error(f"Ошибка при отправке инцидента #{incident_id}: {e}")