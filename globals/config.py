import os
from dotenv import load_dotenv
import json 

load_dotenv()

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]


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


#Управление сервером VPN
def load_servers():
    raw = os.getenv("WG_SERVERS", "[]")
    try:
        data = json.loads(raw)
        servers = []
        for item in data:
            # поддержка старых вариантов ключей
            name = item.get("name") or item.get("VPN-основной") or item.get("VPN-BBH")
            if not name:
                continue
            servers.append({
                "name": name,
                "API_URL": item.get("API_URL") or item.get("ip") or item.get("IP"),
                "API_KEY": item.get("API_KEY") or item.get("api key") or item.get("api_key")
            })
        return servers
    except Exception as e:
        print(f"[CONFIG] Ошибка чтения WG_SERVERS: {e}")
        return []

print("[CONFIG DEBUG] WG_SERVERS raw =", os.getenv("WG_SERVERS"))
print("[CONFIG DEBUG] Parsed =", load_servers())

WG_SERVERS = load_servers()

print("[CONFIG DEBUG] WG_SERVERS raw =", os.getenv("WG_SERVERS"))
print("[CONFIG DEBUG] Parsed =", load_servers())