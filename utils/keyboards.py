from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from logger.logger import logger

async def get_incident_keyboard(incident_id: int, db):
    """Генерация клавиатуры для инцидента"""
    try:
        incident = await db.get_incident(incident_id)
        if not incident:
            logger.warning(f"Incedent #{incident_id} not found for keyboard")
            return None

        status = incident['status']

        if status == 'open':
            return InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Take", callback_data=f"take_{incident_id}"),
                    InlineKeyboardButton(text="Reject", callback_data=f"reject_{incident_id}")
                ]
            ])

        elif status == 'in_progress':
            return InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Reassign", callback_data=f"reassign_{incident_id}"),
                    InlineKeyboardButton(text="Close", callback_data=f"close_{incident_id}")
                ]
            ])

        elif status in ['closed', 'rejected']:
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Reopen", callback_data=f"reopen_{incident_id}")]
            ])

        return None

    except Exception as e:
        logger.error(f"Error generating keyboard for incident #{incident_id}: {e}", exc_info=True)
        return None