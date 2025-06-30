from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database  # Убрали create_incident
from logger.logger import logger
from globals import GROUP_ID, TOPIC_ID
from datetime import datetime

router = Router()

class IncidentStates(StatesGroup):
    waiting_for_comment = State()

# Новый обработчик для кнопок изменения статуса
@router.callback_query(F.data.startswith("status_"))
async def change_incident_status(callback: CallbackQuery, state: FSMContext, db: Database):
    action, incident_id, new_status = callback.data.split("_")
    user = callback.from_user.username or callback.from_user.full_name
    
    try:
        # Обновляем статус в базе данных
        await db.update_incident_status(
            incident_id=int(incident_id),
            status=new_status
        )
        
        # Формируем текст для уведомления
        status_text = {
            "open": "открыт",
            "in_progress": "взят в работу",
            "rejected": "отклонен",
            "closed": "закрыт"
        }.get(new_status, new_status)
        
        emoji = {
            "open": "🔓",
            "in_progress": "🛠️",
            "rejected": "❌",
            "closed": "🔒"
        }.get(new_status, "ℹ️")
        
        text = (
            f"{emoji} <b>Инцидент #{incident_id} {status_text}</b>\n"
            f"👤 Пользователь: {user}\n"
            f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Отправляем уведомление в группу
        await callback.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=TOPIC_ID,
            text=text,
            parse_mode="HTML"
        )
        
        await callback.answer(f"Статус изменен на: {status_text}")
        await callback.message.edit_reply_markup(
            reply_markup=generate_incident_buttons(int(incident_id), new_status)
        )
        
    except Exception as e:
        logger.error(f"Ошибка изменения статуса инцидента #{incident_id}: {e}")
        await callback.answer("❌ Ошибка обновления статуса")

# Функция генерации кнопок (вынесена для повторного использования)
def generate_incident_buttons(incident_id: int, current_status: str = "open") -> InlineKeyboardMarkup:
    buttons = []
    
    if current_status == "open":
        buttons.append([
            InlineKeyboardButton(text="Взять в работу", callback_data=f"take_{incident_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{incident_id}")
        ])
    elif current_status == "in_progress":
        buttons.append([
            InlineKeyboardButton(text="Закрыть", callback_data=f"close_{incident_id}"),
            InlineKeyboardButton(text="Вернуть в открытые", callback_data=f"status_{incident_id}_open")
        ])
    elif current_status == "rejected":
        buttons.append([
            InlineKeyboardButton(text="Вернуть в открытые", callback_data=f"status_{incident_id}_open")
        ])
    elif current_status == "closed":
        buttons.append([
            InlineKeyboardButton(text="Переоткрыть", callback_data=f"status_{incident_id}_open")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="История статусов", callback_data=f"history_{incident_id}")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Остальные обработчики остаются без изменений, но добавляем вызов create_incident
# ... [ваш существующий код take_in_work, reject_incident, close_incident] ...

# Модифицируем обработчик комментариев
@router.message(StateFilter(IncidentStates.waiting_for_comment))
async def process_comment(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    action = data.get("action")
    incident_id = data.get("incident_id")
    original_message_id = data.get("original_message_id")
    user_id = data.get("user_id")
    username = data.get("username")
    comment = message.text.strip()

    if not comment:
        await message.answer("❌ Комментарий не может быть пустым. Пожалуйста, напишите комментарий.")
        return

    try:
        new_status = ""
        emoji = ""
        action_text = ""
        
        if action == "take":
            new_status = "in_progress"
            emoji = "🛠️"
            action_text = "взят в работу"
            await db.update_incident(
                incident_id=incident_id,
                status=new_status,
                assigned_to=f"{username} (ID: {user_id})",
                comment=comment
            )
            
        elif action == "reject":
            new_status = "rejected"
            emoji = "❌"
            action_text = "отклонен"
            await db.update_incident(
                incident_id=incident_id,
                status=new_status,
                closed_by=f"{username} (ID: {user_id})",
                comment=comment
            )
            
        elif action == "close":
            new_status = "closed"
            emoji = "🔒"
            action_text = "закрыт"
            await db.update_incident(
                incident_id=incident_id,
                status=new_status,
                closed_by=f"{username} (ID: {user_id})",
                comment=comment
            )
        
        text = (
            f"{emoji} <b>Инцидент #{incident_id} {action_text}</b>\n"
            f"👤 Пользователь: {username}\n"
            f"📝 Комментарий: {comment}\n"
            f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Обновляем оригинальное сообщение
        await message.bot.edit_message_reply_markup(
            chat_id=GROUP_ID,
            message_id=original_message_id,
            message_thread_id=TOPIC_ID,
            reply_markup=generate_incident_buttons(incident_id, new_status)
        )

        # Отправляем уведомление в группу
        await message.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=TOPIC_ID,
            text=text,
            parse_mode="HTML"
        )
        
        await message.answer("✔️ Действие успешно выполнено!")
        logger.info(f"Инцидент #{incident_id} обработан: действие={action}, пользователь={username}")

    except Exception as e:
        logger.error(f"Ошибка при обработке инцидента #{incident_id}: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.")
    
    finally:
        await state.clear()