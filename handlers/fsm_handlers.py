from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import Database
from logger.logger import logger
from globals import GROUP_ID, TOPIC_ID
from datetime import datetime
from utils.messages import format_incident_message
from utils.keyboards import get_incident_keyboard
from datetime import datetime, timezone

router = Router()

class IncidentStates(StatesGroup):
    waiting_for_comment = State()
    waiting_for_reassign = State()

async def safe_edit_message(
    bot, 
    chat_id: int, 
    message_id: int, 
    text: str, 
    reply_markup: InlineKeyboardMarkup = None
):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return True
    except TelegramBadRequest as e:
        if "message to edit not found" in str(e).lower() or "message is not modified" in str(e).lower():
            logger.warning(f"Message edit failed: {e}")
        else:
            logger.error(f"Telegram API error during message edit: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error during message edit: {e}", exc_info=True)
    return False

@router.callback_query(F.data.startswith("take_"))
async def take_in_work(callback: CallbackQuery, state: FSMContext):
    try:
        incident_id = int(callback.data.split("_")[1])
        user = callback.from_user
        username = f"@{user.username}" if user.username else user.full_name
        user_id = user.id

        logger.info(f"User {username} (ID: {user_id}) started taking incident #{incident_id}")

        await state.update_data(
            action="take",
            incident_id=incident_id,
            original_message_id=callback.message.message_id,
            user_id=user_id,
            username=username
        )

        await callback.message.answer("✍️ Please enter a comment for taking the incident:")
        await state.set_state(IncidentStates.waiting_for_comment)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in take_in_work: {e}", exc_info=True)
        await callback.answer("An error occurred, please try later")

@router.callback_query(F.data.startswith("reject_"))
async def reject_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        incident_id = int(callback.data.split("_")[1])
        user = callback.from_user
        username = f"@{user.username}" if user.username else user.full_name
        user_id = user.id

        logger.info(f"User {username} (ID: {user_id}) started rejecting incident #{incident_id}")

        await state.update_data(
            action="reject",
            incident_id=incident_id,
            original_message_id=callback.message.message_id,
            user_id=user_id,
            username=username
        )
        await callback.message.answer("✍️ Please enter a comment for rejecting the incident:")
        await state.set_state(IncidentStates.waiting_for_comment)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in reject_incident: {e}", exc_info=True)
        await callback.answer("An error occurred, please try later")

@router.callback_query(F.data.startswith("close_"))
async def close_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        incident_id = int(callback.data.split("_")[1])
        user = callback.from_user
        username = f"@{user.username}" if user.username else user.full_name
        user_id = user.id

        logger.info(f"User {username} (ID: {user_id}) started closing incident #{incident_id}")

        await state.update_data(
            action="close",
            incident_id=incident_id,
            original_message_id=callback.message.message_id,
            user_id=user_id,
            username=username
        )
        await callback.message.answer("✍️ Please enter a comment for closing the incident:")
        await state.set_state(IncidentStates.waiting_for_comment)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in close_incident: {e}", exc_info=True)
        await callback.answer("An error occurred, please try later")

@router.callback_query(F.data.startswith("reassign_"))
async def reassign_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        incident_id = int(callback.data.split("_")[1])
        user = callback.from_user
        username = f"@{user.username}" if user.username else user.full_name

        logger.info(f"User {username} started reassigning incident #{incident_id}")

        await state.update_data(
            action="reassign",
            incident_id=incident_id,
            original_message_id=callback.message.message_id
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Assign to me", callback_data=f"selfassign_{incident_id}")],
            [InlineKeyboardButton(text="Cancel", callback_data="cancel_reassign")]
        ])

        await callback.message.answer(
            "👥 Specify user for reassignment (@username):",
            reply_markup=keyboard
        )
        await state.set_state(IncidentStates.waiting_for_reassign)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in reassign_incident: {e}", exc_info=True)
        await callback.answer("An error occurred, please try later")

@router.callback_query(F.data.startswith("selfassign_"))
async def self_assign_incident(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        incident_id = int(callback.data.split("_")[1])
        user = callback.from_user
        username = f"@{user.username}" if user.username else user.full_name
        user_id = user.id

        logger.info(f"User {username} (ID: {user_id}) self-assigned to incident #{incident_id}")

        success = await db.update_incident(
            incident_id=incident_id,
            assigned_to_username=username,
            assigned_to_user_id=user_id
        )

        if not success:
            await callback.answer("❌ Failed to update incident")
            return

        incident = await db.get_incident(incident_id)
        if not incident:
            await callback.answer("❌ Incident not found")
            return

        text = format_incident_message(incident)
        keyboard = await get_incident_keyboard(incident_id, db)

        await safe_edit_message(
            callback.bot,
            GROUP_ID,
            callback.message.message_id - 1,
            text,
            keyboard
        )

        await callback.message.answer(f"✅ You've been assigned to incident #{incident_id}")
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in self_assign_incident: {e}", exc_info=True)
        await callback.answer("An error occurred, please try later")

@router.callback_query(F.data == "cancel_reassign")
async def cancel_reassign(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Reassignment canceled")
    await callback.answer()

@router.message(StateFilter(IncidentStates.waiting_for_reassign))
async def process_reassign(message: Message, state: FSMContext, db: Database):
    try:
        data = await state.get_data()
        incident_id = data.get("incident_id")
        username = message.text.strip()

        if not username.startswith("@"):
            await message.answer("❌ Invalid format. Use @username format")
            return

        logger.info(f"Reassigning incident #{incident_id} to {username}")

        success = await db.update_incident(
            incident_id=incident_id,
            assigned_to_username=username,
            assigned_to_user_id=None  # User ID unknown for manual assignment
        )

        if not success:
            await message.answer("❌ Failed to update incident")
            return

        incident = await db.get_incident(incident_id)
        if not incident:
            await message.answer("❌ Incident not found")
            return

        text = format_incident_message(incident)
        keyboard = await get_incident_keyboard(incident_id, db)

        await safe_edit_message(
            message.bot,
            GROUP_ID,
            data.get("original_message_id"),
            text,
            keyboard
        )

        await message.answer(f"✅ Incident #{incident_id} reassigned to {username}")
        await state.clear()
    except Exception as e:
        logger.error(f"Error in process_reassign: {e}", exc_info=True)
        await message.answer("❌ An error occurred during reassignment")

@router.message(StateFilter(IncidentStates.waiting_for_comment))
async def process_comment(message: Message, state: FSMContext, db: Database):
    try:
        data = await state.get_data()
        action = data.get("action")
        incident_id = data.get("incident_id")
        original_message_id = data.get("original_message_id")
        user_id = data.get("user_id")
        username = data.get("username")
        comment = message.text.strip()

        if not comment:
            await message.answer("❌ Comment cannot be empty")
            return

        logger.info(f"Processing comment for incident #{incident_id}, action: {action}")

        update_data = {}
        if action == "take":
            update_data = {
                "status": "in_progress",
                "assigned_to_username": username,
                "assigned_to_user_id": user_id,
                "comment": comment
            }
        elif action == "reject":
            update_data = {
                "status": "rejected",
                "closed_by_username": username,
                "closed_by_user_id": user_id,
                "closed_at": datetime.now(timezone.utc),
                "comment": comment
            }
        elif action == "close":
            update_data = {
                "status": "closed",
                "closed_by_username": username,
                "closed_by_user_id": user_id,
                "closed_at": datetime.now(timezone.utc),  
                "comment": comment
            }

        success = await db.update_incident(incident_id, **update_data)
        if not success:
            await message.answer("❌ Failed to update incident")
            return

        incident = await db.get_incident(incident_id)
        if not incident:
            await message.answer("❌ Incident not found")
            return

        text = format_incident_message(incident)
        keyboard = await get_incident_keyboard(incident_id, db)

        await safe_edit_message(
            message.bot,
            GROUP_ID,
            original_message_id,
            text,
            keyboard
        )

        action_text = {
            "take": "taken in work",
            "reject": "rejected",
            "close": "closed"
        }.get(action, "processed")

        await message.answer(f"✅ Incident #{incident_id} {action_text}!")
        logger.info(f"Incedent #{incident_id} processed: action={action}, user={username}")

    except Exception as e:
        logger.error(f"Error processing comment: {e}", exc_info=True)
        await message.answer("❌ An error occurred while processing your request")
    finally:
        await state.clear()