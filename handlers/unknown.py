from aiogram import Router
from aiogram.types import Message
from logger import logger  # Импортируем наш логгер

router = Router()

@router.message()
async def unknown_command(message: Message):
    if message.text and message.text.startswith("/"):
        # Получаем информацию о пользователе
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else "без username"
        
        # Формируем сообщение для лога
        log_message = (
            f"Пользователь {user_id} ({username}) - "
            f"Попытка вызвать несуществующую команду {message.text}"
        )
        
        # Логируем с уровнем WARNING
        logger.warning(log_message)
        
        # Отправляем ответ пользователю
        await message.answer("Неизвестная команда. Введите /help для списка доступных команд.")