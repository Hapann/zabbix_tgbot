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
    
    # Время создания (UTC-0)
    created_time_utc = incident['created_at']
    if created_time_utc.tzinfo is None:
        created_time_utc = created_time_utc.replace(tzinfo=timezone.utc)
    
    # Время закрытия (UTC-0), если есть
    closed_time_utc = None
    if incident.get('closed_at'):
        closed_time_utc = incident['closed_at']
        if closed_time_utc.tzinfo is None:
            closed_time_utc = closed_time_utc.replace(tzinfo=timezone.utc)

    # Форматируем время создания (UTC-0)
    created_time_str = created_time_utc.strftime('%Y-%m-%d %H:%M:%S UTC-0')

    text = (
        f"{emoji} <b>Инцидент №{incident['id']}</b>\n"
        f"🔹 <b>Событие:</b> {incident['event']}\n"
        f"🌐 <b>На узле:</b> {incident['node']}\n"
        f"⚠️ <b>Триггер:</b> {incident['trigger']}\n"
        f"🔄 <b>Состояние:</b> {status_display}\n"
        f"🔴 <b>Уровень критичности:</b> {incident['severity']}\n"
        f"📄 <b>Подробности:</b> {incident['details']}\n"
        f"🕒 <b>Время создания:</b> {created_time_str}"
    )

    # Добавляем информацию о взятии в работу, если есть
    if incident.get('assigned_to_username') and incident['status'] == 'in_progress':
        text += f"\n👤 <b>В работе у:</b> {incident['assigned_to_username']}"

    # Добавляем информацию о закрытии (UTC-0)
    if closed_time_utc:
        closed_time_str = closed_time_utc.strftime('%Y-%m-%d %H:%M:%S UTC-0')
        text += f"\n🔒 <b>Закрыл:</b> {incident['closed_by_username']}"
        text += f"\n🕒 <b>Время закрытия:</b> {closed_time_str}"
        
        # Расчёт длительности (UTC-0)
        duration = closed_time_utc - created_time_utc
        total_seconds = duration.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        
        # Форматируем вывод в зависимости от длительности
        if hours > 0:
            text += f"\n⏱️ <b>Время решения:</b> {hours}ч {minutes}м"
        elif minutes > 0:
            text += f"\n⏱️ <b>Время решения:</b> {minutes}м {seconds}с"
        else:
            text += f"\n⏱️ <b>Время решения:</b> {seconds}с"
    
    # Добавляем комментарий, если есть
    if incident.get('comment'):
        text += f"\n💬 <b>Комментарий:</b> {incident['comment']}"
    
    return text