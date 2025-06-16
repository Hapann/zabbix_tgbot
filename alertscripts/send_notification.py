#!/usr/bin/env python3
import sys
import asyncio
from services.message_utils import send_incident_notification
from database import db
from config import config


async def main(event_id, subject, message):
    # Инициализация базы данных
    await db.create_pool()
    await db.create_tables()

    # Отправка уведомления
    await send_incident_notification(event_id, subject, message)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: send_notification.py <event_id> <subject> <message>")
        sys.exit(1)

    event_id = sys.argv[1]
    subject = sys.argv[2]
    message = sys.argv[3]

    asyncio.run(main(event_id, subject, message))
