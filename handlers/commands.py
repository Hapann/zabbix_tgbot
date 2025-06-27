from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database
from globals import GROUP_ID, TOPIC_ID
from logger import logger

router = Router()

# Кнопки для инцидента
def incident_buttons(incident_id: int, status: str):
    if status == "new":
        buttons = [
            InlineKeyboardButton(text="В работу", callback_data=f"take_{incident_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{incident_id}")
        ]
    elif status == "in_progress":
        buttons = [
            InlineKeyboardButton(text="Закрыть", callback_data=f"close_{incident_id}")
        ]
    else:
        buttons = []
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

@router.message(Command(commands=["help"]))
async def help_handler(message: Message):
    await message.answer(
        "Этот бот принимает алерты из Zabbix и позволяет управлять инцидентами.\n"
        "Команды:\n"
        "/help - помощь\n"
        "/rules - инструкция по работе с ботом"
    )

@router.message(Command(commands=["rules"]))
async def rules_handler(message: Message):
    await message.answer(
        "Правила работы с ботом:\n"
        "1. При получении алерта вы можете взять инцидент в работу или отклонить.\n"
        "2. При взятии в работу необходимо будет оставить комментарий при закрытии.\n"
        "3. При отклонении также требуется комментарий.\n"
        "4. Все действия фиксируются в базе."
    )

# Обработка кнопок (callback)
@router.callback_query(F.data.startswith("take_"))
async def take_in_work(callback: CallbackQuery, db: Database):
    incident_id = int(callback.data.split("_")[1])
    await callback.message.answer("Пожалуйста, напишите комментарий для взятия в работу.")
    # Сохраняем состояние, что ждем комментарий (нужно реализовать FSM, упрощу)
    # Для учебного примера можно просто отправить сообщение и ждать следующий текст

@router.callback_query(F.data.startswith("reject_"))
async def reject_incident(callback: CallbackQuery, db: Database):
    incident_id = int(callback.data.split("_")[1])
    await callback.message.answer("Пожалуйста, напишите комментарий для отклонения инцидента.")

@router.callback_query(F.data.startswith("close_"))
async def close_incident(callback: CallbackQuery, db: Database):
    incident_id = int(callback.data.split("_")[1])
    await callback.message.answer("Пожалуйста, напишите комментарий для закрытия инцидента.")
    

async def send_incident_to_group(bot, incident_id, event, node, trigger, status, severity, details):
    text = (
        f"<b>Событие:</b> {event}\n"
        f"<b>На узле:</b> {node}\n"
        f"<b>Сработал триггер:</b> {trigger}\n"
        f"<b>Состояние:</b> {status}\n"
        f"<b>Уровень критичности:</b> {severity}\n"
        f"<b>Подробности:</b> {details}"
    )
    keyboard = incident_buttons(incident_id, status)
    await bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        reply_markup=keyboard,
        message_thread_id=TOPIC_ID,
        parse_mode="HTML"
    )