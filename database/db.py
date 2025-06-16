from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import urllib.parse
from dotenv import load_dotenv
import sys

# Загрузка переменных окружения
load_dotenv()

# Получение данных для подключения к БД из переменных окружения
POSTGRES_USER = urllib.parse.quote_plus(os.getenv("POSTGRES_USER", ""))
POSTGRES_PASSWORD = urllib.parse.quote_plus(os.getenv("POSTGRES_PASSWORD", ""))
POSTGRES_HOST = urllib.parse.quote_plus(os.getenv("POSTGRES_HOST", ""))
POSTGRES_DB = urllib.parse.quote_plus(os.getenv("POSTGRES_DB", ""))
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Создание строки подключения
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

try:
    # Создание движка
    engine = create_engine(DATABASE_URL)

    # Проверка соединения
    with engine.connect() as conn:
        pass
    print(
        f"Успешное подключение к PostgreSQL по адресу {POSTGRES_HOST}:{POSTGRES_PORT}"
    )
except Exception as e:
    print(f"Не удалось подключиться к PostgreSQL: {e}")
    print("Убедитесь, что PostgreSQL запущен и доступен по указанным параметрам.")
    print("Проверьте параметры подключения в файле .env")
    sys.exit(1)  # Завершаем программу с ошибкой

# Создание базового класса для моделей
Base = declarative_base()

# Создание сессии
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Определение моделей
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    zabbix_token = Column(String, nullable=True)

    # Отношения
    subscriptions = relationship("Subscription", back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    host_id = Column(String)

    # Отношения
    user = relationship("User", back_populates="subscriptions")


# Функция для создания таблиц (синхронная)
def create_tables():
    Base.metadata.create_all(bind=engine)


# Асинхронная функция-обертка для совместимости с async кодом
async def init_db():
    try:
        create_tables()
        print("База данных успешно инициализирована")
    except Exception as e:
        print(f"Ошибка при инициализации базы данных: {e}")
        sys.exit(1)  # Завершаем программу с ошибкой
