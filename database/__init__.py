# Если вы перешли на синхронный подход
from .db import (
    SessionLocal as async_session,
    Base,
    create_tables as init_db,
    User,
    Subscription,
)
