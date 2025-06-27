import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger():
    logger = logging.getLogger("zabbix_bot")
    logger.setLevel(logging.INFO)
    
    # Формат сообщений
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Консольный вывод
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Путь к папке logs относительно текущего файла
    logs_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
    # Создаём папку logs, если её нет
    os.makedirs(logs_dir, exist_ok=True)
    
    # Путь к файлу лога
    log_file = os.path.join(logs_dir, 'bot.log')
    
    # Файловый вывод с ротацией
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()