import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    GROUP_ID = int(os.getenv("GROUP_ID"))
    TOPIC_ID = int(os.getenv("TOPIC_ID")) if os.getenv("TOPIC_ID") else None
    DB_URL = os.getenv("DB_URL")
    ZABBIX_URL = os.getenv("ZABBIX_URL")
    ZABBIX_USER = os.getenv("ZABBIX_USER")
    ZABBIX_PASSWORD = os.getenv("ZABBIX_PASSWORD")

config = Config()