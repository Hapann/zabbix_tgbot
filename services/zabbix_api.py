import httpx
from config import config

async def acknowledge_event(event_id: str, comment: str):
    async with httpx.AsyncClient() as client:
        # Authenticate
        auth_data = {
            "jsonrpc": "2.0",
            "method": "user.login",
            "params": {
                "user": config.ZABBIX_USER,
                "password": config.ZABBIX_PASSWORD
            },
            "id": 1
        }
        auth_resp = await client.post(config.ZABBIX_URL, json=auth_data)
        auth_token = auth_resp.json().get("result")
        
        # Acknowledge event
        ack_data = {
            "jsonrpc": "2.0",
            "method": "event.acknowledge",
            "params": {
                "eventids": event_id,
                "message": f"Resolved via Telegram: {comment}",
                "action": 1  # Close problem
            },
            "auth": auth_token,
            "id": 2
        }
        await client.post(config.ZABBIX_URL, json=ack_data)