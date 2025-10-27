import logging
import sys
import io
from pathlib import Path
from datetime import datetime

from globals.config import (
    LOG_FILE_MAX_SIZE,
    LOG_FILE_BACKUP_COUNT,
    LOG_ROTATE,
    LOG_ROTATE_BY_SIZE,
    LOG_ROTATE_BY_TIME,
    LOG_LEVEL,
)

# Принудительно ставим UTF-8 для stdout (на случай работы в окружениях без поддержки)
if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# === Кастомные обработчики ===
class DailyFolderFileHandler(logging.FileHandler):
    """
    FileHandler, который каждый день создаёт новую папку logs/YYYY-MM-DD/
    и туда кладёт bot.log.
    """

    def __init__(self, basename, *args, **kwargs):
        self.basename = basename
        self.current_day = datetime.now().strftime("%Y-%m-%d")
        log_dir = Path("logs") / self.current_day
        log_dir.mkdir(parents=True, exist_ok=True)
        filename = log_dir / basename
        super().__init__(filename, *args, **kwargs)

    def emit(self, record):
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.current_day:
            # Новый день — создаём новую папку
            self.current_day = today
            self.close()
            log_dir = Path("logs") / self.current_day
            log_dir.mkdir(parents=True, exist_ok=True)
            self.baseFilename = str(log_dir / self.basename)
            self.stream = self._open()
        super().emit(record)


class UTF8RotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Handler для поддержки UTF-8 и ротации по размеру"""
    def __init__(self, filename, **kwargs):
        super().__init__(filename, encoding="utf-8", **kwargs)


# === Конфигурация логирования ===
log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --- Создаём основной обработчик (в зависимости от настроек в config) ---
if LOG_ROTATE and LOG_ROTATE_BY_TIME:
    file_handler = DailyFolderFileHandler("bot.log", encoding="utf-8")
elif LOG_ROTATE and LOG_ROTATE_BY_SIZE:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = UTF8RotatingFileHandler(
        filename=logs_dir / "bot.log",
        maxBytes=LOG_FILE_MAX_SIZE,
        backupCount=LOG_FILE_BACKUP_COUNT,
    )
else:
    # Без ротации — обычный файл
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(logs_dir / "bot.log", encoding="utf-8")

file_handler.setLevel(log_level)
file_handler.setFormatter(formatter)

# --- Консольный вывод ---
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)
console_handler.setFormatter(formatter)

# --- Настройка root-логгера ---
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Отключаем шумные/дебажные модули
for lib in [
    "telegram",
    "telegram.ext",
    "telegram.bot",
    "aiogram",
    "httpcore",
    "httpx",
    "httpcore.http11",
    "httpcore.connection",
    "asyncio",
]:
    lib_logger = logging.getLogger(lib)
    lib_logger.setLevel(logging.WARNING)
    lib_logger.propagate = True

# Основной логгер
logger = logging.getLogger("zabbix_bot")
logger.setLevel(log_level)

# Для совместимости с другими частями проекта
handlers = [file_handler, console_handler]