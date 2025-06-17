FROM python:3.10-slim

WORKDIR /app

# Установка зависимостей для PostgreSQL
RUN apt-get update && \
    apt-get install -y libpq-dev gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаем папку для логов
RUN mkdir -p /logs

# Копируем исходный код
COPY . .

# Запуск приложения
CMD ["python", "main.py"]