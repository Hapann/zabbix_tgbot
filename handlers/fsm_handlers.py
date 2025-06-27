from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database
from logger import logger

router = Router()

# Определяем состояния
class IncidentStates(StatesGroup):
    waiting_for_comment = State()

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

# Словарь для хранения текущего действия и инцидента в FSMContext
# Можно хранить в FSMContext напрямую

@router.callback_query(F.data.startswith("take_"))
async def take_in_work(callback: CallbackQuery, state: FSMContext):
    incident_id = int(callback.data.split("_")[1])
    await state.update_data(action="take", incident_id=incident_id)
    await callback.message.answer("Пожалуйста, напишите комментарий для взятия инцидента в работу.")
    await IncidentStates.waiting_for_comment.set()
    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def reject_incident(callback: CallbackQuery, state: FSMContext):
    incident_id = int(callback.data.split("_")[1])
    await state.update_data(action="reject", incident_id=incident_id)
    await callback.message.answer("Пожалуйста, напишите комментарий для отклонения инцидента.")
    await IncidentStates.waiting_for_comment.set()
    await callback.answer()

@router.callback_query(F.data.startswith("close_"))
async def close_incident(callback: CallbackQuery, state: FSMContext):
    incident_id = int(callback.data.split("_")[1])
    await state.update_data(action="close", incident_id=incident_id)
    await callback.message.answer("Пожалуйста, напишите комментарий для закрытия инцидента.")
    await IncidentStates.waiting_for_comment.set()
    await callback.answer()

# Обработка комментария от пользователя
@router.message(StateFilter(IncidentStates.waiting_for_comment))
async def process_comment(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    action = data.get("action")
    incident_id = data.get("incident_id")
    comment = message.text.strip()

    if not comment:
        await message.answer("Комментарий не может быть пустым. Пожалуйста, напишите комментарий.")
        return

    user = message.from_user.username or message.from_user.full_name

    if action == "take":
        await db.update_status(incident_id, "in_progress", user, comment)
        text = f"Инцидент #{incident_id} взят в работу с комментарием: {comment}"

    elif action == "reject":
        await db.reject_incident(incident_id, user, comment)
        text = f"Инцидент #{incident_id} отклонён с комментарием: {comment}"

    elif action == "close":
        await db.close_incident(incident_id, user, comment)
        text = f"Инцидент #{incident_id} закрыт с комментарием: {comment}"

    else:
        await message.answer("Неизвестное действие. Попробуйте снова.")
        await state.clear()
        return

    # Отправляем сообщение в топик группы
    await message.bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        message_thread_id=TOPIC_ID
    )

    await message.answer(text)
    await state.clear()