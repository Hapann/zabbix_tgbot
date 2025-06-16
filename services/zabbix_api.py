import httpx
from config import config
import logging

logger = logging.getLogger(__name__)

class ZabbixAPI:
    def __init__(self):
        self.url = config.ZABBIX_URL
        self.auth_token = None
        self.auth_user = config.ZABBIX_USER
        self.auth_password = config.ZABBIX_PASSWORD

    async def login(self):
        """Аутентификация в Zabbix API"""
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "user.login",
                    "params": {
                        "user": self.auth_user,
                        "password": self.auth_password
                    },
                    "id": 1,
                    "auth": None
                }
                response = await client.post(self.url, json=payload)
                result = response.json()
                
                if 'result' in result:
                    self.auth_token = result['result']
                    logger.info("Успешная аутентификация в Zabbix API")
                    return True
                else:
                    logger.error(f"Ошибка аутентификации: {result.get('error', {})}")
                    return False
        except Exception as e:
            logger.exception(f"Ошибка подключения к Zabbix API: {str(e)}")
            return False

    async def acknowledge_event(self, event_id, comment):
        """Подтверждение события в Zabbix"""
        if not self.auth_token:
            if not await self.login():
                return False
        
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "event.acknowledge",
                    "params": {
                        "eventids": event_id,
                        "message": f"Resolved via Telegram: {comment}",
                        "action": 1  # Закрыть проблему
                    },
                    "auth": self.auth_token,
                    "id": 2
                }
                response = await client.post(self.url, json=payload)
                result = response.json()
                
                if 'result' in result:
                    logger.info(f"Событие {event_id} успешно закрыто в Zabbix")
                    return True
                else:
                    logger.error(f"Ошибка закрытия события: {result.get('error', {})}")
                    return False
        except Exception as e:
            logger.exception(f"Ошибка при закрытии события: {str(e)}")
            return False

# Создаем глобальный экземпляр API
zabbix_api = ZabbixAPI()