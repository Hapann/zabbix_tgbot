from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def get_incident_keyboard(incident_id: int, db):
    """Генерация клавиатуры для инцидента с использованием существующего подключения к БД"""
    incident = await db.get_incident(incident_id)
    
    if not incident:
        return None
        
    status = incident['status']
    
    if status == 'open':
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="В работу", callback_data=f"take_{incident_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{incident_id}")
            ]
        ])
        
    elif status == 'in_progress':
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Переназначить", callback_data=f"reassign_{incident_id}"),
                InlineKeyboardButton(text="Закрыть", callback_data=f"close_{incident_id}")
            ]
        ])
        
    elif status in ['closed', 'rejected']:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Переоткрыть", callback_data=f"reopen_{incident_id}")]
        ])
        
    return None