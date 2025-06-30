from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database
from logger.logger import logger
from globals import GROUP_ID, TOPIC_ID
from datetime import datetime
from utils.messages import format_incident_message
from utils.keyboards import get_incident_keyboard

router = Router()

class IncidentStates(StatesGroup):
    waiting_for_comment = State()
    waiting_for_reassign = State()

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

@router.callback_query(F.data.startswith("reassign_"))
async def reassign_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    incident_id = int(callback.data.split("_")[1])
    user = callback.from_user.username or callback.from_user.full_name
    
    logger.info(f"Пользователь {user} начал переназначение инцидента #{incident_id}")
    
    await state.update_data(
        action="reassign", 
        incident_id=incident_id,
        original_message_id=callback.message.message_id
    )
    
    # В реальной системе здесь можно получить список пользователей из БД
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назначить на меня", callback_data=f"selfassign_{incident_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_reassign")]
    ])
    
    await callback.message.answer(
        "👥 Укажите пользователя для переназначения (в формате @username):",
        reply_markup=keyboard
    )
    await IncidentStates.waiting_for_reassign.set()
    await callback.answer()

@router.callback_query(F.data.startswith("selfassign_"))
async def self_assign_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    incident_id = int(callback.data.split("_")[1])
    user = callback.from_user.username or callback.from_user.full_name
    user_id = callback.from_user.id
    
    logger.info(f"Пользователь {user} (ID: {user_id}) назначил себя на инцидент #{incident_id}")
    
    # Обновляем ответственного
    await db.update_incident(
        incident_id=incident_id,
        assigned_to=f"{user} (ID: {user_id})"
    )
    
    # Обновляем оригинальное сообщение
    incident = await db.get_incident(incident_id)
    text = format_incident_message(incident)
    keyboard = await get_incident_keyboard(incident_id, db)
    
    await callback.bot.edit_message_text(
        chat_id=GROUP_ID,
        message_id=callback.message.message_id - 1,  # Предполагаем, что оригинальное сообщение на 1 выше
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await callback.message.answer(f"✅ Вы назначены ответственным за инцидент #{incident_id}")
    await state.clear()
    await callback.answer()

@router.message(StateFilter(IncidentStates.waiting_for_reassign))
async def process_reassign(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    incident_id = data.get("incident_id")
    username = message.text.strip()
    
    if not username.startswith("@"):
        await message.answer("❌ Неверный формат. Укажите пользователя в формате @username")
        return
    
    logger.info(f"Переназначение инцидента #{incident_id} на {username}")
    
    # Обновляем ответственного
    await db.update_incident(
        incident_id=incident_id,
        assigned_to=username
    )
    
    # Обновляем оригинальное сообщение
    incident = await db.get_incident(incident_id)
    text = format_incident_message(incident)
    keyboard = await get_incident_keyboard(incident_id, db)
    
    await message.bot.edit_message_text(
        chat_id=GROUP_ID,
        message_id=data.get("original_message_id"),
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await message.answer(f"✅ Инцидент #{incident_id} переназначен на {username}")
    await state.clear()

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
        action_text = ""
        
        if action == "take":
            new_status = "in_progress"
            action_text = "взят в работу"
            await db.update_incident(
                incident_id=incident_id,
                status=new_status,
                assigned_to=f"{username} (ID: {user_id})",
                comment=comment
            )
            
        elif action == "reject":
            new_status = "rejected"
            action_text = "отклонен"
            await db.update_incident(
                incident_id=incident_id,
                status=new_status,
                closed_by=f"{username} (ID: {user_id})",
                closed_at=datetime.now(),
                comment=comment
            )
            
        elif action == "close":
            new_status = "closed"
            action_text = "закрыт"
            await db.update_incident(
                incident_id=incident_id,
                status=new_status,
                closed_by=f"{username} (ID: {user_id})",
                closed_at=datetime.now(),
                comment=comment
            )
        
        # Получаем обновленные данные инцидента
        incident = await db.get_incident(incident_id)
        text = format_incident_message(incident)
        keyboard = await get_incident_keyboard(incident_id, db)
        
        # Обновляем оригинальное сообщение
        await message.bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=original_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

        # Отправляем уведомление о выполнении действия
        await message.answer(f"✅ Инцидент #{incident_id} {action_text}!")
        logger.info(f"Инцидент #{incident_id} обработан: действие={action}, пользователь={username}")

    except Exception as e:
        logger.error(f"Ошибка при обработке инцидента #{incident_id}: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.")
    
    finally:
        await state.clear()