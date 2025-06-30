import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from aiogram import Bot
from logger.logger import logger
from globals import BOT_TOKEN, GROUP_ID, TOPIC_ID

router = APIRouter()

class ZabbixAlert(BaseModel):
    incident_id: int
    event: str
    node: str
    trigger: str
    severity: str
    details: str

@router.on_event("startup")
async def startup_event():
    logger.info("Zabbix API handler started")

@router.post("/alert")
async def receive_alert(alert: ZabbixAlert):
    try:
        logger.info(f"Received Zabbix alert: #{alert.incident_id}")
        
        # Формирование сообщения
        text = (
            f"🚨 <b>Новый инцидент #{alert.incident_id}</b>\n"
            f"🔹 <b>Событие:</b> {alert.event}\n"
            f"🌐 <b>На узле:</b> {alert.node}\n"
            f"⚠️ <b>Триггер:</b> {alert.trigger}\n"
            f"🔄 <b>Состояние:</b> открыт\n"
            f"🔴 <b>Уровень критичности:</b> {alert.severity}\n"
            f"📄 <b>Подробности:</b> {alert.details}\n"
            f"🕒 <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Отправка в Telegram
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=int(TOPIC_ID),
            text=text,
            parse_mode="HTML"
        )
        
        return {"status": "success"}
    
    except Exception as e:
        logger.error(f"Error processing alert: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))