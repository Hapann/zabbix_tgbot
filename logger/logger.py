import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

LOG_LEVEL = logging.INFO

class UTF8RotatingFileHandler(RotatingFileHandler):
    """Handler для поддержки UTF-8 в логах"""
    def __init__(self, filename, **kwargs):
        super().__init__(filename, encoding='utf-8', **kwargs)

def setup_logger():
    logger = logging.getLogger("zabbix_bot")
    logger.setLevel(LOG_LEVEL)

    # Очищаем существующие обработчики
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Консольный вывод
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Файловый вывод с UTF-8
    logs_dir = Path(__file__).parent.parent / 'logs'
    try:
        logs_dir.mkdir(exist_ok=True, parents=True)
        log_file = logs_dir / 'bot.log'
        
        # Проверяем доступность файла для записи
        if not log_file.exists():
            log_file.touch()

        file_handler = UTF8RotatingFileHandler(
            filename=log_file,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=10          # 10 backup files
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Проверяем запись в файл
        logger.debug("File logger initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize file logger: {str(e)}")

    additional_loggers = [
        "telegram",
        "telegram.ext",
        "telegram.bot",
        "httpcore",
        "httpx",
        "httpcore.http11",
        "httpcore.connection",
        "asyncio"
    ]

    for logger_name in additional_loggers:
        additional_logger = logging.getLogger(logger_name)
        additional_logger.setLevel(logging.WARNING)
        additional_logger.addHandler(console_handler)
        
        # Добавляем файловый обработчик только если он был успешно создан
        if 'file_handler' in locals():
            additional_logger.addHandler(file_handler)

    return logger

logger = setup_logger()