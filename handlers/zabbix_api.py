import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from aiogram import Bot
from logger.logger import logger
from globals import BOT_TOKEN, GROUP_ID, TOPIC_ID
from utils.messages import format_incident_message
from utils.keyboards import get_incident_keyboard

router = APIRouter()

class ZabbixAlert(BaseModel):
    incident_id: int
    event: str
    node: str
    trigger: str
    severity: str
    details: str

@router.post("/alert")
async def receive_alert(alert: ZabbixAlert, request: Request):
    try:
        logger.info(f"Received Zabbix alert: #{alert.incident_id}")
        
        # Получаем экземпляр базы данных из состояния приложения
        db = request.app.state.db
        
        # Сохранение в базу данных
        incident_id = await db.create_incident({
            "event": alert.event,
            "node": alert.node,
            "trigger": alert.trigger,
            "severity": alert.severity,
            "details": alert.details,
            "status": "open",
            "assigned_to_username": None,
            "assigned_to_user_id": None,
            "closed_by_username": None,
            "closed_by_user_id": None,
            "message_id": None  # Будет обновлено после отправки сообщения
        })
        
        if incident_id == -1:
            raise HTTPException(status_code=500, detail="Failed to save incident")
        
        # Получаем данные инцидента
        incident = await db.get_incident(incident_id)
        text = format_incident_message(incident)
        
        # Передаём существующий экземпляр db в функцию
        keyboard = await get_incident_keyboard(incident_id, db)

        # Отправка в Telegram
        async with Bot(token=BOT_TOKEN) as bot:
            message = await bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=int(TOPIC_ID),
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Сохраняем ID сообщения в базу данных
            await db.update_incident(
                incident_id=incident_id,
                message_id=message.message_id
            )
         
        return {"status": "success", "message_id": message.message_id}
    
    except Exception as e:
        logger.error(f"Error processing alert: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))