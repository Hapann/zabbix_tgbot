import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

# Уровень логирования можно легко менять в одном месте
LOG_LEVEL = logging.DEBUG

def setup_logger():
    logger = logging.getLogger("zabbix_bot")
    logger.setLevel(LOG_LEVEL)
    
    # Формат сообщений
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Консольный вывод
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Путь к папке logs (используем Path для более надежной работы с путями)
    logs_dir = Path(__file__).parent.parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    
    # Путь к файлу лога
    log_file = logs_dir / 'bot.log'
    
    # Файловый вывод с ротацией без ограничения количества файлов
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=0,         # 0 означает неограниченное количество файлов
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # Переименовываем файлы при ротации (bot.log → bot1.log → bot2.log и т.д.)
    def namer(name):
        base, ext = os.path.splitext(name)
        if base[-1].isdigit():
            num = int(base[-1]) + 1
            return f"{base[:-1]}{num}{ext}"
        return f"{base}1{ext}"
    
    file_handler.namer = namer
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()