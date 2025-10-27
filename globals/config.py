import os
import json
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# --- Настройки базы данных / API ---
DB_DSN = os.getenv("DATABASE_URL")

# --- Telegram настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
TOPIC_ID = os.getenv("TOPIC_ID")

# --- Администраторы ---
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# --- Настройки логирования ---
LOG_FILE_MAX_SIZE_MB = 5  # Максимальный размер одного файла (МБ)
LOG_FILE_MAX_SIZE = LOG_FILE_MAX_SIZE_MB * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 10  # Кол-во старых файлов, сохраняемых в ротации

LOG_ROTATE = True             # Главный флаг ротации логов
LOG_ROTATE_BY_SIZE = True     # Ротация по размеру
LOG_ROTATE_BY_TIME = True     # Ротация по датам (папки logs/YYYY-MM-DD)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Проверки обязательных переменных ---
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env файле")

if not GROUP_ID:
    raise ValueError("GROUP_ID не задан в .env файле")

if not DB_DSN:
    raise ValueError("DATABASE_URL не задан в .env файле")


# --- Загрузка списка VPN-серверов из JSON в .env ---
def load_servers():
    raw = os.getenv("WG_SERVERS", "[]")
    try:
        data = json.loads(raw)
        servers = []
        for item in data:
            name = item.get("name") or item.get("VPN-основной") or item.get("VPN-BBH")
            if not name:
                continue
            servers.append({
                "name": name,
                "API_URL": item.get("API_URL") or item.get("ip") or item.get("IP"),
                "API_KEY": item.get("API_KEY") or item.get("api key") or item.get("api_key"),
            })
        return servers
    except Exception as e:
        print(f"[CONFIG] Ошибка чтения WG_SERVERS: {e}")
        return []


def get_today_log_dir():
    """Возвращает путь к сегодняшней директории логов (logs/YYYY-MM-DD)."""
    return os.path.join("logs", datetime.now().strftime("%Y-%m-%d"))


# --- Загружаем VPN-серверы ---
WG_SERVERS = load_servers()

# Отладочная информация
# print("[CONFIG DEBUG] WG_SERVERS raw =", os.getenv("WG_SERVERS"))
# print("[CONFIG DEBUG] Parsed =", WG_SERVERS)