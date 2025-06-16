# handlers/callbacks.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from database import db

router = Router()

class CommentState(StatesGroup):
    waiting_comment = State()

@router.callback_query(F.data.startswith("take:"))
async def take_incident(callback: CallbackQuery):
    event_id = callback.data.split(":")[1]
    user = callback.from_user
    username = f"@{user.username}" if user.username else user.full_name
    
    # Обновляем статус в БД
    await db.execute(
        "UPDATE incidents SET status = 'in_progress', assigned_to = $1 "
        "WHERE event_id = $2 AND status = 'open'",
        username, event_id
    )
    
    # Проверяем, обновилась ли запись
    incident = await db.fetchrow(
        "SELECT * FROM incidents WHERE event_id = $1", event_id
    )
    
    if incident and incident['status'] == 'in_progress':
        # Обновляем сообщение
        await update_incident_message(incident)
        await callback.answer(f"Инцидент взят в работу!")
    else:
        await callback.answer("Не удалось взять инцидент в работу")

@router.callback_query(F.data.startswith(("close:", "reject:")))
async def handle_resolution(callback: CallbackQuery, state: FSMContext):
    action, event_id = callback.data.split(":")[:2]
    await state.update_data(action=action, event_id=event_id)
    await state.set_state(CommentState.waiting_comment)
    await callback.message.answer(
        f"Введите комментарий для {'закрытия' if action == 'close' else 'отклонения'}:",
        reply_to_message_id=callback.message.message_id
    )

@router.message(CommentState.waiting_comment)
async def process_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data['action']
    event_id = data['event_id']
    comment = message.text
    status = 'closed' if action == 'close' else 'rejected'
    
    # Обновляем инцидент в БД
    await db.execute(
        "UPDATE incidents SET status = $1, resolution_comment = $2 "
        "WHERE event_id = $3",
        status, comment, event_id
    )
    
    # Получаем обновленные данные
    incident = await db.fetchrow(
        "SELECT * FROM incidents WHERE event_id = $1", event_id
    )
    
    if incident:
        # Обновляем сообщение
        await update_incident_message(incident, remove_buttons=True)
        
        # Закрываем событие в Zabbix
        await zabbix_api.acknowledge_event(event_id, comment)
    
    await state.clear()

async def update_incident_message(incident: dict, remove_buttons=False):
    status_text = {
        'open': "🟡 Открыт",
        'in_progress': "🔴 В работе",
        'closed': "🟢 Закрыт",
        'rejected': "⚪ Отклонен"
    }
    
    text = f"{incident['original_text']}\n\n"
    text += f"*Статус:* {status_text[incident['status']]}\n"
    
    if incident['assigned_to']:
        text += f"*Исполнитель:* {incident['assigned_to']}\n"
    
    if incident['resolution_comment']:
        text += f"*Комментарий:* {incident['resolution_comment']}"
    
    reply_markup = None
    if not remove_buttons and incident['status'] == 'in_progress':
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Закрыть", callback_data=f"close:{incident['event_id']}")],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"reject:{incident['event_id']}")]
        ])
    
    await bot.edit_message_text(
        chat_id=incident['chat_id'],
        message_id=incident['message_id'],
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )