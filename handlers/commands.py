from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from database.db import Database
from logger.logger import logger
from utils.messages import format_incident_message
from utils.keyboards import get_incident_keyboard
from globals import GROUP_ID, TOPIC_ID
from datetime import datetime

router = Router()

def log_command(message: Message, command: str):
    """Логирование вызова команды"""
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    logger.info(f"Пользователь {user_id} ({username}) - Успешно вызвана команда {command}")

@router.message(Command(commands=["help"]))
async def help_handler(message: Message):
    log_command(message, "/help")
    await message.answer(
        "🤖 Этот бот принимает алерты из Zabbix и позволяет управлять инцидентами.\n\n"
        "📋 Команды:\n"
        "/help - помощь\n"
        "/rules - инструкция по работе с ботом\n"
        "/stats - статистика по инцидентам\n"
        "/active - список активных инцидентов"
    )

@router.message(Command(commands=["rules"]))
async def rules_handler(message: Message):
    log_command(message, "/rules")
    await message.answer(
        "📜 Правила работы с ботом:\n\n"
        "1. При получении алерта вы можете взять инцидент в работу или отклонить.\n"
        "2. При взятии в работу необходимо будет оставить комментарий.\n"
        "3. При закрытии или отклонении также требуется комментарий.\n"
        "4. Все действия фиксируются в базе данных.\n"
        "5. Ответственный может переназначить инцидент другому сотруднику.\n"
        "6. Закрытые инциденты можно переоткрыть при необходимости."
    )

@router.message(Command(commands=["stats"]))
async def stats_handler(message: Message, db: Database):
    log_command(message, "/stats")
    try:
        # Получаем статистику из базы данных
        async with db.pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM incidents")
            open_count = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE status = 'open'")
            in_progress = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE status = 'in_progress'")
            closed = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE status = 'closed'")
            rejected = await conn.fetchval("SELECT COUNT(*) FROM incidents WHERE status = 'rejected'")
        
        response = (
            "📊 Статистика инцидентов:\n\n"
            f"• Всего инцидентов: {total}\n"
            f"• Открыто: {open_count}\n"
            f"• В работе: {in_progress}\n"
            f"• Закрыто: {closed}\n"
            f"• Отклонено: {rejected}"
        )
        await message.answer(response)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("⚠️ Произошла ошибка при получении статистики. Попробуйте позже.")

@router.message(Command(commands=["active"]))
async def active_incidents_handler(message: Message, db: Database):
    log_command(message, "/active")
    try:
        # Получаем активные инциденты
        async with db.pool.acquire() as conn:
            incidents = await conn.fetch(
                "SELECT * FROM incidents WHERE status IN ('open', 'in_progress') ORDER BY created_at DESC"
            )
        
        if not incidents:
            await message.answer("ℹ️ Активных инцидентов нет.")
            return
            
        response = "🚨 Активные инциденты:\n\n"
        for incident in incidents:
            incident_dict = dict(incident)
            response += f"• #{incident_dict['id']} - {incident_dict['event']} ({incident_dict['status']})\n"
        
        await message.answer(response)
    except Exception as e:
        logger.error(f"Ошибка при получении активных инцидентов: {e}")
        await message.answer("⚠️ Произошла ошибка при получении списка инцидентов. Попробуйте позже.")