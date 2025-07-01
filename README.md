Zabbix Telegram Bot
Описание бота

Этот бот предназначен для обработки алертов из Zabbix и управления инцидентами через Telegram. Основные функции:

    Получение алертов из Zabbix через API

    Создание инцидентов в базе данных

    Управление жизненным циклом инцидентов (взятие в работу, закрытие, отклонение)

    Статистика и просмотр активных инцидентов

    Назначение ответственных за инциденты

Функциональность
Основные команды:
Команда	Описание
/help	Показать справку по доступным командам
/rules	Показать правила работы с ботом
/stats	Показать статистику по инцидентам
/active	Показать список активных инцидентов
Управление инцидентами:

    Взять в работу: доступно для статуса "open"

    Отклонить: доступно для статуса "open"

    Закрыть: доступно для статуса "in_progress"

    Переназначить: доступно для статуса "in_progress"

    Переоткрыть: доступно для статусов "closed" и "rejected"

Установка и настройка
Необходимые компоненты

    Python 3.10+

    PostgreSQL 12+

    Docker (опционально, для контейнеризации)

Подготовка к запуску

    Создайте файл .env в корне проекта:

bash

touch .env

    Заполните .env по примеру:

ini

# Telegram
BOT_TOKEN=your_bot_token
GROUP_ID=-111111111111  # ID группы (отрицательный для супергрупп)
TOPIC_ID=123             # ID темы (если используется)

# Database
DB_USER=zabbix_bot_user
DB_PASS=secure_password
DB_NAME=zabbix_bot_db
DB_HOST=localhost
DB_PORT=5432
DATABASE_URL=postgres://zabbix_bot_user:secure_password@localhost:5432/zabbix_bot_db

Переменные окружения
Переменная	Обязательная	Описание
BOT_TOKEN	Да	Токен вашего Telegram бота
GROUP_ID	Да	ID группы, куда будут отправляться уведомления (отрицательный для супергрупп)
TOPIC_ID	Нет	ID темы в группе (если используется)
DB_USER	Да	Пользователь PostgreSQL
DB_PASS	Да	Пароль пользователя PostgreSQL
DB_NAME	Да	Имя базы данных
DB_HOST	Да	Хост базы данных
DB_PORT	Да	Порт базы данных
DATABASE_URL	Да	Полный URL подключения к БД
Запуск
Без Docker

    Установите зависимости:

bash

pip install -r requirements.txt

    Запустите бота:

bash

python main.py

С Docker

    Создайте необходимые директории:

bash

mkdir -p dbdata logs
chmod -R 775 dbdata logs

    Запустите контейнеры:

bash

docker-compose -f docker-compose-new.yml up -d --build

Структура проекта
text

zabbix_tgbot/
├── database/          # Скрипты работы с БД
├── handlers/          # Обработчики команд и сообщений
├── logger/            # Логирование
├── utils/             # Вспомогательные утилиты
├── main.py            # Основной скрипт
├── Dockerfile         # Конфигурация Docker
├── docker-compose.yml # Конфигурация Docker Compose
├── requirements.txt   # Зависимости Python
└── README.md          # Этот файл

Логирование

Логи сохраняются в директории logs/ в файле bot.log. Уровень логирования можно изменить в logger/logger.py.
Лицензия

MIT License