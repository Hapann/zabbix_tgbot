import os
import logging
from dotenv import load_dotenv

load_dotenv()
app_logger = logging.getLogger('zabbix_bot')
app_logger.setLevel(logging.INFO)

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    GROUP_ID = int(os.getenv("GROUP_ID"))
    TOPIC_ID = int(os.getenv("TOPIC_ID")) if os.getenv("TOPIC_ID") else None

    # Database
    DB_URL = os.getenv("DB_URL")

    # Zabbix
    ZABBIX_URL = os.getenv("ZABBIX_URL")
    ZABBIX_USER = os.getenv("ZABBIX_USER")
    ZABBIX_PASSWORD = os.getenv("ZABBIX_PASSWORD")

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/info.log")


config = Config()


def setup_logger():
    """Настройка логгера приложения"""
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(config.LOG_LEVEL)

    # File handler
    file_handler = logging.FileHandler(config.LOG_FILE)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


app_logger = setup_logger()
