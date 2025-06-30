def format_incident_message(incident: dict) -> str:
    status_display = {
        'open': 'открыт',
        'in_progress': 'в работе',
        'rejected': 'отклонен',
        'closed': 'закрыт'
    }.get(incident['status'], incident['status'])
    
    emoji = {
        'open': '🔓',
        'in_progress': '🛠️',
        'rejected': '❌',
        'closed': '🔒'
    }.get(incident['status'], 'ℹ️')
    
    text = (
        f"{emoji} <b>Инцидент #{incident['id']}</b>\n"
        f"🔹 <b>Событие:</b> {incident['event']}\n"
        f"🌐 <b>На узле:</b> {incident['node']}\n"
        f"⚠️ <b>Триггер:</b> {incident['trigger']}\n"
        f"🔄 <b>Состояние:</b> {status_display}\n"
        f"🔴 <b>Уровень критичности:</b> {incident['severity']}\n"
        f"📄 <b>Подробности:</b> {incident['details']}\n"
        f"🕒 <b>Время создания:</b> {incident['created_at'].strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    # Добавляем информацию об ответственном, если есть
    if incident.get('assigned_to'):
        text += f"\n👤 <b>Ответственный:</b> {incident['assigned_to']}"
        
    # Добавляем информацию о закрытии, если есть
    if incident.get('closed_by'):
        text += f"\n🔒 <b>Закрыл:</b> {incident['closed_by']}"
        
    # Добавляем время решения, если есть
    if incident.get('closed_at'):
        duration = (incident['closed_at'] - incident['created_at'])
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        text += f"\n⏱️ <b>Время решения:</b> {int(hours)}ч {int(minutes)}м"
        
    # Добавляем комментарий, если есть
    if incident.get('comment'):
        text += f"\n💬 <b>Комментарий:</b> {incident['comment']}"
        
    return text