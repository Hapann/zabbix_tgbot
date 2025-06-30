import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
TOPIC_ID = os.getenv("TOPIC_ID")
DB_DSN = os.getenv("DATABASE_URL")

# Проверка обязательных переменных
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env file")

if not GROUP_ID:
    raise ValueError("GROUP_ID is not set in .env file")

if not DB_DSN:
    raise ValueError("DATABASE_URL is not set in .env file")