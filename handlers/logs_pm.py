import os
import glob
import html
from pathlib import Path
from aiogram import Router
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from logger.logger import logger
from globals.config import ADMIN_IDS  # список id админов

router = Router()

LOGS_DIR = Path("logs")
DEFAULT_LINES = 50
TELEGRAM_LIMIT = 4000  # лимит текста в одном сообщении


# ---------- Вспомогательные функции ----------

async def _tail(filepath: str, lines: int = 50) -> list[str]:
    """Вернуть последние N строк файла."""
    logger.debug(f"_tail(): Читаем {lines} строк из файла {filepath}")
    try:
        with open(filepath, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            block_size = 1024

            data = b""
            line_count = 0

            while end > 0 and line_count <= lines:
                read_size = block_size if end >= block_size else end
                end -= read_size
                f.seek(end)
                block = f.read(read_size)
                data = block + data
                line_count = data.count(b"\n")

        text = data.decode(errors="ignore")
        logger.debug(f"_tail(): Успешно прочитано примерно {len(text)} символов")
        return text.strip().splitlines()[-lines:]
    except Exception as e:
        logger.error(f"_tail(): Ошибка при чтении {filepath}: {e}", exc_info=True)
        raise


def _list_log_dirs() -> dict[str, list[str]]:
    """Вернуть словарь {дата: [файлы]}."""
    dirs = {}
    logger.debug(f"_list_log_dirs(): Ищем подкаталоги логов в {LOGS_DIR}")
    if not LOGS_DIR.exists():
        logger.warning(f"_list_log_dirs(): Папка {LOGS_DIR} не существует")
        return {}

    for subdir in sorted(LOGS_DIR.iterdir()):
        if subdir.is_dir():
            files = [f.name for f in sorted(subdir.glob('*.log'))]
            if files:
                dirs[subdir.name] = files
                logger.debug(f"_list_log_dirs(): Найдены файлы {files} в папке {subdir.name}")
    return dirs


def _latest_file_in_date(date: str) -> str | None:
    """Найти последний измененный файл в папке даты."""
    date_dir = LOGS_DIR / date
    logger.debug(f"_latest_file_in_date(): Ищем последние логи за {date} в {date_dir}")
    if not date_dir.exists():
        logger.warning(f"_latest_file_in_date(): Папки {date_dir} не существует")
        return None

    files = list(date_dir.glob("*.log"))
    if not files:
        logger.warning(f"_latest_file_in_date(): В папке {date} нет логов")
        return None

    files.sort(key=os.path.getmtime, reverse=True)
    logger.debug(f"_latest_file_in_date(): Самый свежий файл: {files[0]}")
    return str(files[0])


# ---------- Хэндлер ----------

@router.message(Command("logs"))
async def cmd_logs(message: Message):
    telegram_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name
    args = message.text.split()

    logger.info(f"/logs вызвал [{telegram_id}|@{username}] → args={args}")

    # --- проверка прав ---
    if telegram_id not in ADMIN_IDS:
        await message.answer(
            "❌ Такой команды не существует!\n\n"
            "ℹ️ Посмотреть список всех доступных команд можно здесь: /help"
        )
        logger.warning(f"⛔ Пользователь [{telegram_id}|@{username}] попытался вызвать /logs без доступа")
        return

    # --- неправильный вызов без аргументов ---
    if len(args) == 1:
        await message.answer(
            "❌ Неправильный вызов.\n\n"
            "Использование:\n"
            "📂 `/logs list` — список доступных дат и файлов\n"
            "🗓 `/logs date YYYY-MM-DD` — выгрузить последний лог за дату\n"
            "📄 `/logs date YYYY-MM-DD filename.log` — выгрузить конкретный файл\n"
            "📜 `/logs date YYYY-MM-DD N` — последние N строк из последнего файла\n"
            "📜 `/logs date YYYY-MM-DD filename.log N` — последние N строк из файла\n",
            parse_mode="Markdown"
        )
        logger.debug("/logs: некорректный вызов без аргументов")
        return

    # --- список папок и файлов ---
    if args[1] == "list":
        data = _list_log_dirs()
        if not data:
            await message.answer("⚠️ Логи не найдены")
            logger.warning("/logs list: Логи не найдены")
            return

        lines = ["📂 Доступные логи:"]
        for date, files in data.items():
            lines.append(f"\n🗓 {date}:")
            for f in files:
                lines.append(f"  └ {f}")

        safe_text = html.escape("\n".join(lines))
        await message.answer(f"<pre>{safe_text}</pre>", parse_mode="HTML")
        logger.info(f"[admin:{telegram_id}] запросил список логов, найдено {len(data)} дат")
        return

    # --- работа с датой ---
    if args[1] == "date":
        if len(args) < 3:
            await message.answer(
                "❌ Неверный аргумент!\n\n"
                "Использование:\n"
                "🗓 `/logs date YYYY-MM-DD`\n"
                "📄 `/logs date YYYY-MM-DD filename.log`\n"
                "📜 `/logs date YYYY-MM-DD N`\n"
                "📜 `/logs date YYYY-MM-DD filename.log N`",
                parse_mode="Markdown"
            )
            logger.warning("/logs date вызван без даты → отказ")
            return

        date = args[2]
        file_name = None
        lines = None

        if len(args) == 5 and args[4].isdigit():
            file_name = args[3]
            lines = int(args[4])
            logger.debug(f"/logs date: file={file_name}, lines={lines}")
        elif len(args) == 4 and args[3].isdigit():
            lines = int(args[3])
            logger.debug(f"/logs date: lines={lines}")
        elif len(args) == 4:
            file_name = args[3]
            logger.debug(f"/logs date: file={file_name}")
        else:
            logger.debug("/logs date: только дата → берём весь последний файл")

        # выбор файла
        if file_name:
            log_file = LOGS_DIR / date / file_name
            if not log_file.exists():
                await message.answer(f"⚠️ Файл {file_name} не найден в {date}")
                logger.warning(f"/logs date {date}: Файл {file_name} не найден")
                return
            log_file = str(log_file)
        else:
            log_file = _latest_file_in_date(date)
            if not log_file:
                await message.answer(f"⚠️ Нет логов за {date}")
                logger.warning(f"/logs date {date}: Логов нет")
                return

        # загрузка содержимого
        try:
            if lines:  # последние N строк
                logger.debug(f"/logs: читаем последние {lines} строк из {log_file}")
                lines_data = await _tail(log_file, lines=lines)
                text = "\n".join(lines_data)

                if len(text) > TELEGRAM_LIMIT:
                    logger.debug("/logs: текст слишком длинный → отправляем как файл")
                    doc = FSInputFile(log_file)
                    await message.answer_document(doc)
                else:
                    safe_text = html.escape(text)
                    await message.answer(
                        f"📜 Последние {lines} строк из {os.path.basename(log_file)}:\n\n<pre>{safe_text}</pre>",
                        parse_mode="HTML"
                    )

                logger.info(f"[admin:{telegram_id}] получил {lines} строк из {log_file}")

            else:  # файл целиком
                logger.debug(f"/logs: отправляем весь файл {log_file}")
                doc = FSInputFile(log_file)
                await message.answer_document(doc)
                logger.info(f"[admin:{telegram_id}] выгрузил файл {log_file} полностью")

        except Exception as e:
            await message.answer(f"❌ Ошибка чтения логов: {e}")
            logger.error(f"/logs: Ошибка при чтении {log_file}: {e}", exc_info=True)
        return

    # --- неизвестная подкоманда ---
    await message.answer(
        "❌ Неверный аргумент!\n\n"
        "Использование:\n"
        "📂 `/logs list`\n"
        "🗓 `/logs date YYYY-MM-DD`\n"
        "📄 `/logs date YYYY-MM-DD filename.log`\n"
        "📜 `/logs date YYYY-MM-DD N`\n"
        "📜 `/logs date YYYY-MM-DD filename.log N`",
        parse_mode="Markdown"
    )
    logger.warning(f"/logs неизвестная подкоманда: args={args}")


# === Регистрация хэндлера ===
def register_logs_pm_handler(app):
    app.include_router(router)
    logger.info("Обработчик /logs зарегистрирован")