from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database
from logger.logger import logger
from globals import GROUP_ID, TOPIC_ID
from datetime import datetime

router = Router()

class IncidentStates(StatesGroup):
    waiting_for_comment = State()

@router.callback_query(F.data.startswith("take_"))
async def take_in_work(callback: CallbackQuery, state: FSMContext, db: Database):
    incident_id = int(callback.data.split("_")[1])
    user = callback.from_user.username or callback.from_user.full_name
    user_id = callback.from_user.id
    
    logger.info(f"Пользователь {user} (ID: {user_id}) начал взятие инцидента #{incident_id} в работу")
    
    await state.update_data(
        action="take", 
        incident_id=incident_id,
        original_message_id=callback.message.message_id,
        user_id=user_id,
        username=user
    )
    await callback.message.answer("✍️ Пожалуйста, напишите комментарий для взятия инцидента в работу:")
    await IncidentStates.waiting_for_comment.set()
    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def reject_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    incident_id = int(callback.data.split("_")[1])
    user = callback.from_user.username or callback.from_user.full_name
    user_id = callback.from_user.id
    
    logger.info(f"Пользователь {user} (ID: {user_id}) начал отклонение инцидента #{incident_id}")
    
    await state.update_data(
        action="reject", 
        incident_id=incident_id,
        original_message_id=callback.message.message_id,
        user_id=user_id,
        username=user
    )
    await callback.message.answer("✍️ Пожалуйста, напишите комментарий для отклонения инцидента:")
    await IncidentStates.waiting_for_comment.set()
    await callback.answer()

@router.callback_query(F.data.startswith("close_"))
async def close_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    incident_id = int(callback.data.split("_")[1])
    user = callback.from_user.username or callback.from_user.full_name
    user_id = callback.from_user.id
    
    logger.info(f"Пользователь {user} (ID: {user_id}) начал закрытие инцидента #{incident_id}")
    
    await state.update_data(
        action="close", 
        incident_id=incident_id,
        original_message_id=callback.message.message_id,
        user_id=user_id,
        username=user
    )
    await callback.message.answer("✍️ Пожалуйста, напишите комментарий для закрытия инцидента:")
    await IncidentStates.waiting_for_comment.set()
    await callback.answer()

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
        if action == "take":
            await db.update_incident(
                incident_id=incident_id,
                status="in_progress",
                assigned_to=f"{username} (ID: {user_id})",
                comment=comment
            )
            
            text = (
                f"✅ <b>Инцидент #{incident_id} взят в работу</b>\n"
                f"👤 Ответственный: {username}\n"
                f"📝 Комментарий: {comment}\n"
                f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Обновляем оригинальное сообщение
            await message.bot.edit_message_reply_markup(
                chat_id=GROUP_ID,
                message_id=original_message_id,
                message_thread_id=TOPIC_ID,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Закрыть", callback_data=f"close_{incident_id}")]
                ])
            )

        elif action == "reject":
            await db.update_incident(
                incident_id=incident_id,
                status="rejected",
                closed_by=f"{username} (ID: {user_id})",
                comment=comment
            )
            
            text = (
                f"❌ <b>Инцидент #{incident_id} отклонен</b>\n"
                f"👤 Пользователь: {username}\n"
                f"📝 Комментарий: {comment}\n"
                f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Удаляем кнопки из оригинального сообщения
            await message.bot.edit_message_reply_markup(
                chat_id=GROUP_ID,
                message_id=original_message_id,
                message_thread_id=TOPIC_ID,
                reply_markup=None
            )

        elif action == "close":
            await db.update_incident(
                incident_id=incident_id,
                status="closed",
                closed_by=f"{username} (ID: {user_id})",
                comment=comment
            )
            
            text = (
                f"🔒 <b>Инцидент #{incident_id} закрыт</b>\n"
                f"👤 Пользователь: {username}\n"
                f"📝 Комментарий: {comment}\n"
                f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Удаляем кнопки из оригинального сообщения
            await message.bot.edit_message_reply_markup(
                chat_id=GROUP_ID,
                message_id=original_message_id,
                message_thread_id=TOPIC_ID,
                reply_markup=None
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