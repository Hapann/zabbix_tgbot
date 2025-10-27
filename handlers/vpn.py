import requests
import zipfile
import json
import subprocess
from dotenv import load_dotenv
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import io, os, base64, shutil
import urllib.parse
from aiogram.types import FSInputFile
from aiogram.types import BufferedInputFile
from hashlib import sha1
from globals.config import WG_SERVERS
from logger.logger import logger


# ===================================================
# Настройки WGDashboard API
# ===================================================
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

router = Router()


# ===================================================
# Вспомогательные функции для REST
# ===================================================
#def wg_request(endpoint, method="GET", payload=None):
#    headers = {"wg-dashboard-apikey": API_KEY, "Content-Type": "application/json"}
#    url = f"{API_URL}{endpoint}"
#    r = requests.request(method, url, json=payload, headers=headers, timeout=10)
#    r.raise_for_status()
#    return r.json()

def wg_request(endpoint, method="GET", payload=None):
    headers = {"wg-dashboard-apikey": API_KEY, "Content-Type": "application/json"}
    url = f"{API_URL}{endpoint}"
#    print(f"[DEBUG] {method} {url} payload={payload}")       # 👈 лог перед запросом
    r = requests.request(method, url, json=payload, headers=headers, timeout=10)
#    print(f"[DEBUG] response {r.status_code}: {r.text}")     # 👈 лог ответа
    r.raise_for_status()
    return r.json()


def get_interfaces():
    resp = wg_request("/api/getWireguardConfigurations")
    return resp.get("data", [])


def get_peers(config_name: str):
    """
    Возвращает все peers, включая заблокированные (restricted).
    """
    try:
        resp = wg_request(f"/api/getWireguardConfigurationInfo?configurationName={config_name}")
    except Exception as e:
        raise RuntimeError(f"Ошибка запроса к WGDashboard: {e}")

    if not resp or "data" not in resp or resp["data"] is None:
        raise RuntimeError(f"Пустой ответ от WGDashboard для {config_name}: {resp}")

    data = resp["data"]

    peers = data.get("configurationPeers", []) or []
    restricted = data.get("configurationRestrictedPeers", []) or []

    for p in restricted:
        p["restricted"] = True

    return peers + restricted


def create_peer(config_name: str, peer_name: str):
    resp = wg_request(f"/api/addPeers/{config_name}", "POST", {"name": peer_name})
    peer_data = resp.get("data", [])
    if not peer_data:
        raise Exception(resp.get("message") or "Не удалось создать peer")
    return peer_data[0].get("id")


def delete_peer(config_name: str, peer_id: str):
    """
    Удаляет peer через новый формат API WGDashboard:
    POST /api/deletePeers/{config_name}
    { "peers": ["<peer_id>"] }
    """
    resp = wg_request(f"/api/deletePeers/{config_name}", "POST", {"peers": [peer_id]})
    return resp.get("status") or resp.get("success", False)


def toggle_config(config_name: str):
    """
    Переключает состояние WireGuard‑конфигурации.
    """
    endpoint = f"/api/toggleWireguardConfiguration?configurationName={config_name}"
    resp = wg_request(endpoint, "GET")
    return resp.get("data"), resp.get("status")


def download_peer_file(config_name: str, peer_id: str):
    """
    Загружает конфигурацию указанного peer через API.
    Возвращает (file_name, file_bytes)
    """
    # peer_id обязательно URI‑кодируем
    encoded_id = urllib.parse.quote(peer_id, safe='')
    endpoint = f"/api/downloadPeer/{config_name}?id={encoded_id}"
    headers = {"wg-dashboard-apikey": API_KEY}
    url = f"{API_URL}{endpoint}"
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", {})
    file_content = data.get("file", "")
    filename = data.get("fileName", "peer.conf")
    return filename, file_content.encode()


def download_all_peers_zip(config_name: str):
    """
    Загружает все peer-конфиги для указанного интерфейса
    и возвращает архив ZIP (filename, bytes).
    Если имена файлов совпадают — добавляет суффиксы (1), (2) и т.д.
    """
    url = f"{API_URL}/api/downloadAllPeers/{config_name}"
    headers = {"wg-dashboard-apikey": API_KEY}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    files = resp.json().get("data", [])

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
        used_names = {}
        for item in files:
            base_name = item.get("fileName", "peer").replace("/", "_").strip()
            file_name = base_name + ".conf"

            # если имя уже встречалось — добавляем суффикс (1), (2), ...
            if file_name in used_names:
                used_names[file_name] += 1
                name_root = base_name
                suffix = used_names[file_name]
                file_name = f"{name_root}({suffix}).conf"
            else:
                used_names[file_name] = 0

            content = item.get("file", "")
            zipf.writestr(file_name, content)

    zip_buffer.seek(0)
    return f"{config_name}_all_peers.zip", zip_buffer.getvalue()


def delete_wireguard_config(config_name: str):
    """Удаляет конфигурацию WireGuard"""
    payload = {"ConfigurationName": config_name}
    resp = wg_request("/api/deleteWireguardConfiguration", "POST", payload)
    return resp.get("status") or False, resp.get("message")


def add_wireguard_config(payload: dict):
    """Создаёт новую конфигурацию WireGuard"""
    resp = wg_request("/api/addWireguardConfiguration", "POST", payload)
    return resp.get("status") or False, resp.get("message")

def generate_private_key() -> str:
    """Генерируем приватный ключ WireGuard через системную утилиту или fallback в Python."""
    wg_path = shutil.which("wg")
    if wg_path:
        return subprocess.check_output([wg_path, "genkey"]).decode().strip()
    return base64.b64encode(os.urandom(32)).decode()

def short_id(pid: str) -> str:
    """Возвращает короткий безопасный идентификатор (до 10 символов) для callback_data"""
    return sha1(pid.encode()).hexdigest()[:10]

# ===================================================
# FSM
# ===================================================
class VPNStates(StatesGroup):
    interface = State()
    peer_name = State()
    peers_cache = State()
    last_menu_id = State()

class AddConfigStates(StatesGroup):
    waiting_json = State()


class PeerEditStates(StatesGroup):
    waiting_field = State()       # ждём, какое поле редактировать
    waiting_value = State()       # ждём новое значение от пользователя
    confirm_change = State()      # подтверждение изменений

class IfaceEditStates(StatesGroup):
    waiting_field = State()
    waiting_value = State()
    confirm_change = State()
    
# ===================================================
# Универсальная безопасная отправка / редактирование
# ===================================================
async def _send_or_edit(target, text, state: FSMContext,
                        parse_mode=None, reply_markup=None, force_new=False):
    data = await state.get_data()
    message_id = data.get("last_menu_id")

    # если есть старое меню и разрешено редактирование
    if message_id and not force_new:
        try:
            await target.bot.edit_message_text(
                chat_id=target.chat.id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            if "can't be edited" not in str(e):
                try:
                    await target.bot.delete_message(target.chat.id, message_id)
                except Exception:
                    pass
            # если нельзя редактировать — создаём заново

    sent = await target.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)
    await state.update_data(last_menu_id=sent.message_id)


# ===================================================
# /vpn — список всех конфигураций
# ===================================================
async def show_interfaces(target, state: FSMContext, force_new=False):
    """
    Отображает список интерфейсов WireGuard для текущего выбранного сервера.
    Меню обновляется в одном сообщении.
    """
    logger.debug("Запуск show_interfaces(force_new=%s)", force_new)
    try:
        configs = get_interfaces()
        logger.info("Получено %d конфигураций интерфейсов.", len(configs))
    except Exception as e:
        logger.exception("Ошибка при получении конфигураций:")
        await _send_or_edit(
            target,
            f"❌ Ошибка получения конфигураций:\n```\n{e}\n```",
            state,
            parse_mode="Markdown",
            force_new=force_new
        )
        return

    if not configs:
        logger.warning("Нет доступных интерфейсов для отображения.")
        await _send_or_edit(
            target, "Нет доступных интерфейсов.", state, force_new=force_new
        )
        return

    inline = []
    for cfg in configs:
        status = "🟢" if cfg.get("Status") else "🔴"
        name = cfg.get("Name", "unknown")
        inline.append([InlineKeyboardButton(text=f"{status} {name}",
                                            callback_data=f"iface:{name}")])

    inline.append([
        InlineKeyboardButton(text="➕ Добавить конфигурацию",
                             callback_data="add_config")
    ])
    inline.append([
        InlineKeyboardButton(text="🔙 К списку серверов", callback_data="back_servers")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=inline)
    logger.debug("Сформировано меню интерфейсов (%d элементов).", len(configs))
    await _send_or_edit(
        target,
        "Выбери конфигурацию:",
        state,
        reply_markup=kb,
        force_new=force_new
    )


@router.message(F.text == "/vpn")
async def cmd_vpn(message: Message, state: FSMContext):
    """
    Первое меню: показывает список серверов из WG_SERVERS.
    Работает в одном сообщении, не создаёт новые.
    """
    from globals.config import WG_SERVERS

    logger.info("Пользователь %s вызвал /vpn", message.from_user.id)

    if not WG_SERVERS:
        logger.warning("WG_SERVERS пуст: нет доступных серверов.")
        await message.answer("⚠️ Не найдено ни одного сервера в WG_SERVERS.")
        return

    inline = [
        [InlineKeyboardButton(text=srv["name"],
                              callback_data=f"select_server:{srv['name']}")]
        for srv in WG_SERVERS
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=inline)
    logger.debug("Сформировано меню выбора серверов (%d шт).", len(WG_SERVERS))

    await _send_or_edit(
        message,
        "🌐 Выбери сервер для управления:",
        state,
        reply_markup=kb,
        force_new=True
    )


@router.callback_query(F.data.startswith("select_server:"))
async def on_server_selected(query: CallbackQuery, state: FSMContext):
    """
    После выбора сервера заменяет текущее сообщение на меню интерфейсов.
    """
    from globals.config import WG_SERVERS

    server_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id if query.from_user else "unknown"
    logger.info("Пользователь %s выбрал сервер '%s'", user_id, server_name)

    srv = next((s for s in WG_SERVERS if s["name"] == server_name), None)

    if not srv:
        logger.error("Сервер '%s' не найден в WG_SERVERS", server_name)
        await query.answer("Сервер не найден", show_alert=True)
        return

    # сохраняем выбранный сервер в FSMContext
    await state.update_data(selected_server=srv)
    logger.debug("FSMContext обновлён: выбран сервер %s", server_name)

    # подменяем глобальные переменные
    global API_URL, API_KEY
    API_URL = srv["API_URL"]
    API_KEY = srv["API_KEY"]

    logger.info("[VPN] Установлен API_URL=%s", API_URL)

    await query.answer(f"✅ {server_name} выбран")
    await show_interfaces(query.message, state, force_new=False)


@router.callback_query(F.data == "back_servers")
async def back_servers(query: CallbackQuery, state: FSMContext):
    """
    Возврат от интерфейсов обратно к списку серверов (редактирует то же сообщение).
    """
    from globals.config import WG_SERVERS

    user_id = query.from_user.id if query.from_user else "unknown"
    logger.info("Пользователь %s вернулся к списку серверов", user_id)

    if not WG_SERVERS:
        logger.warning("WG_SERVERS пуст при возврате к списку серверов.")
        await query.answer("⚠️ Нет доступных серверов.", show_alert=True)
        return

    inline = [
        [InlineKeyboardButton(text=srv["name"],
                              callback_data=f"select_server:{srv['name']}")]
        for srv in WG_SERVERS
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=inline)

    logger.debug("Формируется главное меню серверов (%d шт).", len(WG_SERVERS))
    await _send_or_edit(
        query.message,
        "🌐 Выбери сервер для управления:",
        state,
        reply_markup=kb,
        force_new=False
    )

    await query.answer("↩️ К списку серверов")
    logger.debug("Сообщение обновлено: пользователь %s видит список серверов.", user_id)


# ===================================================
# Список peer'ов конкретного интерфейса
# ===================================================
@router.callback_query(F.data.startswith("iface:"))
async def iface_selected(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    await state.update_data(interface=iface)
    await show_peers(query.message, iface, state)
    await query.answer()


async def show_peers(message: Message, iface: str, state: FSMContext):
    try:
        info = wg_request(f"/api/getWireguardConfigurationInfo?configurationName={iface}")
        conf_info = info.get("data", {}).get("configurationInfo", {})
        iface_enabled = bool(conf_info.get("Status"))
        iface_status = "🟢" if iface_enabled else "🔴"
        data = info.get("data", {})
        peers = data.get("configurationPeers", [])
        restricted_peers = data.get("configurationRestrictedPeers", [])

        # добавляем restricted-признак и объединяем
        for p in restricted_peers:
            p["restricted"] = True
        peers.extend(restricted_peers)

    except Exception as e:
        await _send_or_edit(
            message, f"❌ Ошибка загрузки peers:\n```\n{e}\n```",
            state, parse_mode="Markdown"
        )
        return

    buttons, row = [], []
    short_cache = []
    for p in peers:
        name = (p.get("name") or "(без имени)")[:20]
        pid = p["id"]
        if p.get("restricted"):
            status_dot = "🟡"
        elif p.get("status") == "running":
            status_dot = "🟢"
        else:
            status_dot = "🔴"

        label = f"{status_dot} {name}"
        short_pid = short_id(pid)
        short_cache.append({"id": pid, "short": short_pid, "name": name})

        # теперь в callback_data передаём iface и short_id
        row.append(InlineKeyboardButton(text=label, callback_data=f"peerinfo:{iface}:{short_pid}"))
        if len(row) == 3:
            buttons.append(row); row = []
    if row:
        buttons.append(row)

    toggle_text = "🟥 Выключить интерфейс" if iface_enabled else "🟩 Включить интерфейс"
    buttons.append([
        InlineKeyboardButton(text="📦 Скачать все конфиги", callback_data=f"download_all:{iface}"),
        InlineKeyboardButton(text=toggle_text, callback_data=f"toggle_iface:{iface}")
    ])
    buttons.append([
        InlineKeyboardButton(text="🗑 Удалить конфигурацию", callback_data=f"del_config:{iface}")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh:{iface}"),
        InlineKeyboardButton(text="➕ Добавить peer", callback_data="peer_add")
    ])
    buttons.append([
        InlineKeyboardButton(text="⚙️ Изменить конфигурацию", callback_data=f"iface_edit:{iface}")
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="back_main")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await _send_or_edit(
        message, f"{iface_status} *{iface}* — список peer'ов:",
        state, parse_mode="Markdown", reply_markup=kb
    )
    await state.update_data(peers_cache=short_cache)



# ================================================================
# Список редактирования интерфейса
# ================================================================
@router.callback_query(F.data.startswith("iface_edit:"))
async def iface_edit_start(query: CallbackQuery, state: FSMContext):
    """Показывает список редактируемых полей конфигурации."""
    iface = query.data.split(":", 1)[1]
    logger.info(f"[VPN] Пользователь выбрал редактирование интерфейса {iface}")

    fields = [
        ["Address", "ListenPort"],
        ["PostUp", "PostDown"],
        ["PreUp", "PreDown"],
    ]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f, callback_data=f"iface_field:{iface}:{f}")]
        for row in fields for f in row
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"iface:{iface}")])

    await state.update_data(iface=iface)
    await query.message.edit_text("Выбери параметр для изменения:", reply_markup=kb)
    await query.answer()
    logger.debug(f"[VPN] Интерфейс {iface}: показан список параметров для изменения")


@router.callback_query(F.data.startswith("iface_field:"))
async def iface_field_selected(query: CallbackQuery, state: FSMContext):
    """После выбора поля показывает текущее значение и ждёт ввод нового."""
    _, iface, field = query.data.split(":", 2)
    logger.info(f"[VPN] Пользователь выбрал поле {field} для изменения в интерфейсе {iface}")

    try:
        conf = next((c for c in get_interfaces() if c.get("Name") == iface), None)
        current_value = conf.get(field) if conf and field in conf else "(пусто)"
    except Exception as e:
        logger.exception(f"[VPN] Ошибка при получении данных интерфейса {iface}: {e}")
        await query.answer(f"⚠️ Ошибка: {e}", show_alert=True)
        return

    await state.update_data(iface=iface, field=field, old_value=current_value)
    await state.set_state(IfaceEditStates.waiting_value)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Отмена", callback_data=f"iface:{iface}")]
    ])

    text = (
        f"Введите новое значение для *{field}*.\n"
        f"Текущее: `{current_value}`"
    )
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await query.answer()
    logger.debug(f"[VPN] Интерфейс {iface}, поле {field}: текущее значение '{current_value}' показано пользователю")



# ================================================================
# Подтверждение изменения интерфейса
# ================================================================
@router.message(IfaceEditStates.waiting_value)
async def iface_edit_get_value(message: Message, state: FSMContext):
    """Пользователь вводит новое значение -> просим подтвердить."""
    new_value = message.text.strip()
    data = await state.get_data()
    field = data.get("field")
    old_value = data.get("old_value")
    iface = data.get("iface")

    logger.info(f"[VPN] Интерфейс {iface}, параметр {field}: пользователь ввёл новое значение '{new_value}' "
                f"(старое '{old_value}')")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="iface_confirm_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="iface_confirm_no")
        ]
    ])
    text = (
        f"Изменить `{field}`:\n"
        f"• Было: `{old_value}`\n"
        f"• Стало: `{new_value}`"
    )

    await state.update_data(new_value=new_value)
    await state.set_state(IfaceEditStates.confirm_change)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)



@router.callback_query(F.data == "iface_confirm_yes")
async def iface_confirm_yes(query: CallbackQuery, state: FSMContext):
    """Подтверждение изменения: собирает полную конфигурацию и шлёт updateWireguardConfiguration."""
    data = await state.get_data()
    iface = data.get("iface")
    field = data.get("field")
    new_value = data.get("new_value")

    if not iface:
        logger.warning("[VPN] iface отсутствует при подтверждении изменения интерфейса")
        await query.answer("Ошибка: имя интерфейса отсутствует", show_alert=True)
        await state.clear()
        return

    FIELD_TYPES = {
        "Address": str,
        "ListenPort": int,
        "PostUp": str,
        "PostDown": str,
        "PreUp": str,
        "PreDown": str,
    }

    try:
        conf = next((c for c in get_interfaces() if c.get("Name") == iface), None)
        if not conf:
            logger.warning(f"[VPN] Конфигурация {iface} не найдена при обновлении")
            await query.answer("Конфигурация не найдена", show_alert=True)
            await state.clear()
            return

        update_payload = {
            "Name": iface,
            "Address": conf.get("Address"),
            "ListenPort": int(conf.get("ListenPort") or 0),
            "PostUp": conf.get("PostUp", ""),
            "PostDown": conf.get("PostDown", ""),
            "PreUp": conf.get("PreUp", ""),
            "PreDown": conf.get("PreDown", ""),
            "PrivateKey": conf.get("PrivateKey", ""),
            "PublicKey": conf.get("PublicKey", ""),
            "Protocol": conf.get("Protocol", "wg"),
            "SaveConfig": conf.get("SaveConfig", True),
            "Table": conf.get("Table", "")
        }

        expected_type = FIELD_TYPES.get(field, str)
        if expected_type is int:
            try:
                update_payload[field] = int(new_value)
            except ValueError:
                logger.warning(f"[VPN] Поле {field} ожидало число, получено '{new_value}'")
                await query.answer(f"Поле {field} должно быть числом", show_alert=True)
                return
        else:
            update_payload[field] = str(new_value)

        logger.info(f"[VPN] Обновление интерфейса {iface}: {field}: '{conf.get(field)}' → '{new_value}'")
        logger.debug(f"[VPN] updateWireguardConfiguration payload={update_payload}")

        result = wg_request("/api/updateWireguardConfiguration", "POST", update_payload)
        logger.debug(f"[VPN] Ответ WGDashboard при обновлении {iface}: {result}")

        if not result.get("status"):
            raise RuntimeError(result.get("message") or "WGDashboard вернул status=False")

        logger.info(f"[VPN] Интерфейс {iface} успешно обновлён (поле {field})")
        await query.answer("✅ Конфигурация изменена", show_alert=False)

    except Exception as e:
        logger.exception(f"[VPN] Ошибка при обновлении интерфейса {iface}: {e}")
        await query.answer(f"⚠️ Ошибка: {e}", show_alert=True)
        return

    await state.clear()
    await show_peers(query.message, iface, state)


@router.callback_query(F.data == "iface_confirm_no")
async def iface_confirm_no(query: CallbackQuery, state: FSMContext):
    """Отмена изменения -> возвращаем карточку интерфейса."""
    data = await state.get_data()
    iface = data.get("iface")

    logger.info(f"[VPN] Отмена изменения конфигурации интерфейса {iface} пользователем")

    await query.answer("Отменено", show_alert=False)
    await state.clear()
    await show_peers(query.message, iface, state)


# ================================================================
# Универсальная функция показа карточки peer (вызывается и прямо, и через callbacks)
# ================================================================
async def peer_info_from_data(message: Message, iface: str, peer_short: str, state: FSMContext):
    """Рисует карточку peer по iface и short_id."""
    data = await state.get_data()
    peers_cache = data.get("peers_cache") or []

    peer_id = next((p["id"] for p in peers_cache if p["short"] == peer_short), None)
    if not peer_id:
        await message.answer("Peer не найден")
        return

    peer = next((p for p in get_peers(iface) if p.get("id") == peer_id), None)
    if not peer:
        await message.answer("Peer не найден")
        return

    name = peer.get("name") or "(без имени)"
    is_restricted = bool(peer.get("restricted"))
    is_running = peer.get("status") == "running"

    if is_restricted:
        status_emoji = "🟡 restricted"
    elif is_running:
        status_emoji = "🟢 running"
    else:
        status_emoji = "⚫️ stopped"

    lines = [
        f"*Peer — {name}*",
        f"• Public Key: `{peer.get('id')}`",
        f"• Allowed IPs: `{peer.get('allowed_ip')}`",
        f"• Endpoint Allowed IPs: `{peer.get('endpoint_allowed_ip')}`",
        f"• DNS: `{peer.get('DNS')}`",
        f"• Pre‑Shared Key: `{peer.get('preshared_key')}`",
        f"• MTU: `{peer.get('mtu')}`",
        f"• Keepalive: `{peer.get('keepalive')}`",
        f"• Status: {status_emoji}",
        f"• Last handshake: `{peer.get('latest_handshake')}`",
        f"• Traffic: ↓{peer.get('total_receive')} / ↑{peer.get('total_sent')} GB",
    ]
    text = "\n".join(lines)

    toggle_label = "♻️ Разблокировать" if is_restricted else "🚫 Заблокировать"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать файл", callback_data=f"peer_download:{iface}:{peer_short}")],
        [InlineKeyboardButton(text="⚙️ Изменить peer", callback_data=f"peer_edit:{iface}:{peer_short}")],
        [InlineKeyboardButton(text=toggle_label, callback_data=f"peer_toggle_restrict:{iface}:{peer_short}")],
        [InlineKeyboardButton(text="🗑 Удалить peer", callback_data=f"peer_delask:{iface}:{peer_short}")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data=f"iface:{iface}")],
    ])

    await _send_or_edit(message, text, state, parse_mode="Markdown", reply_markup=kb)


# ===================================================
# Карточка peer + удаление
# ===================================================
@router.callback_query(F.data.startswith("peerinfo:"))
async def peer_info(query: CallbackQuery, state: FSMContext):
    parts = query.data.split(":", 2)
    if len(parts) < 3:
        await query.answer("Неверный формат callback", show_alert=True)
        return
    _, iface, peer_short = parts

    await peer_info_from_data(query.message, iface, peer_short, state)
    await query.answer()


# ========== подтверждение удаления ==========
@router.callback_query(F.data.startswith("peer_delask:"))
async def peer_delete_confirm(query: CallbackQuery, state: FSMContext):
    peer_short = query.data.split(":", 1)[1]
    data = await state.get_data()
    iface = data.get("interface")
    peers_cache = data.get("peers_cache") or []

    peer_id = next((p["id"] for p in peers_cache if p["short"] == peer_short), None)
    peer_name = next((p["name"] for p in peers_cache if p["short"] == peer_short), "(без имени)")

    if not peer_id:
        await query.answer("Peer не найден", show_alert=True)
        return

    text = f"❗ Удалить peer *{peer_name}* из *{iface}*?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"peer_delyes:{peer_short}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"peerinfo:{peer_short}")
        ]
    ])
    await _send_or_edit(query.message, text, state, parse_mode="Markdown", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("peer_delyes:"))
async def peer_delete_yes(query: CallbackQuery, state: FSMContext):
    peer_short = query.data.split(":", 1)[1]
    data = await state.get_data()
    iface = data.get("interface")
    peers_cache = data.get("peers_cache") or []

    peer_id = next((p["id"] for p in peers_cache if p["short"] == peer_short), None)
    name = next((p["name"] for p in peers_cache if p["short"] == peer_short), "(без имени)")

    if not peer_id:
        await query.answer("Peer не найден", show_alert=True)
        return

    try:
        logger.info(f"[VPN] Удаление peer {name} ({peer_id}) из {iface}")
        if delete_peer(iface, peer_id):
            msg = f"❌ Peer *{name}* удалён из `{iface}`"
            logger.info(f"[VPN] Peer {name} успешно удалён из {iface}")
        else:
            msg = f"⚠️ Не удалось удалить peer *{name}*"
            logger.warning(f"[VPN] Не удалось удалить peer {name} ({peer_id})")
    except Exception as e:
        logger.exception(f"[VPN] Исключение при удалении peer {name} ({peer_id}): {e}")
        msg = f"❌ Ошибка при удалении peer:\n```\n{e}\n```"

    await _send_or_edit(query.message, msg, state, parse_mode="Markdown")
    await show_peers(query.message, iface, state)
    await query.answer()

# ===================================================
# Добавление нового peer
# ===================================================
@router.callback_query(F.data == "peer_add")
async def peer_add_start(query: CallbackQuery, state: FSMContext):
    iface = (await state.get_data()).get("interface")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Отмена", callback_data=f"iface:{iface}")]
    ])
    await state.set_state(VPNStates.peer_name)
    await _send_or_edit(query.message,
                        f"Введите имя нового peer для *{iface}* (например `client01`):",
                        state, parse_mode="Markdown", reply_markup=kb)
    await query.answer()


@router.message(VPNStates.peer_name)
async def peer_add_finish(message: Message, state: FSMContext):
    iface = (await state.get_data()).get("interface")
    peer_name = message.text.strip()
    try:
        logger.info(f"[VPN] Создание peer '{peer_name}' в конфигурации {iface}")
        peer_id = create_peer(iface, peer_name)
        logger.info(f"[VPN] Peer '{peer_name}' создан в {iface}, id={peer_id}")
        await message.answer(
            f"✅ Peer *{peer_name}* создан в `{iface}`\nPublic key: `{peer_id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"[VPN] Ошибка создания peer '{peer_name}' в {iface}: {e}")
        await message.answer(f"❌ Ошибка создания peer:\n```\n{e}\n```", parse_mode="Markdown")
    await show_peers(message, iface, state)


# ===================================================
# Блокировать/разблокировать peer
# ===================================================
@router.callback_query(F.data.startswith("peer_toggle_restrict:"))
async def toggle_restrict(query: CallbackQuery, state: FSMContext):
    _, iface, peer_short = query.data.split(":", 2)
    data = await state.get_data()
    peers_cache = data.get("peers_cache") or []
    peer_id = next((p["id"] for p in peers_cache if p["short"] == peer_short), None)
    if not peer_id:
        await query.answer("Peer не найден", show_alert=True)
        return

    try:
        peer = next((p for p in get_peers(iface) if p.get("id") == peer_id), None)
        if not peer:
            await query.answer("Peer не найден", show_alert=True)
            return

        restricted = bool(peer.get("restricted"))
        if restricted:
            endpoint = f"/api/allowAccessPeers/{iface}"
            human = "разблокирован"
        else:
            endpoint = f"/api/restrictPeers/{iface}"
            human = "заблокирован"

        wg_request(endpoint, "POST", {"peers": [peer_id]})
        logger.info(f"[VPN] Peer {peer.get('name')} ({peer_id}) в {iface} {human}")
        await query.answer(f"♻️ Peer {peer.get('name')} {human}", show_alert=False)
        await peer_info(query, state)
    except Exception as e:
        logger.exception(f"[VPN] Ошибка при блокировке peer {peer_id}: {e}")
        await query.answer(f"⚠️ Ошибка: {e}", show_alert=True)


# ===================================================
# Изменить peer
# ===================================================
@router.callback_query(F.data.startswith("peer_edit:"))
async def peer_edit_start(query: CallbackQuery, state: FSMContext):
    # peer_edit:<iface>:<short_id>
    _, iface, peer_short = query.data.split(":", 2)
    data = await state.get_data()
    peers_cache = data.get("peers_cache") or []
    peer_id = next((p["id"] for p in peers_cache if p["short"] == peer_short), None)

    fields = [
        ["name", "allowed_ip"],
        ["endpoint_allowed_ip", "DNS"],
        ["keepalive", "mtu"],
        ["preshared_key", "private_key"],
    ]

    # каждая кнопка включает интерфейс, peer и имя поля
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f, callback_data=f"edit_field:{iface}:{peer_short}:{f}")]
        for row in fields for f in row
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅ Отмена", callback_data=f"peerinfo:{iface}:{peer_short}")])

    await state.update_data(peer_id=peer_id, iface=iface, peer_short=peer_short)
    await _send_or_edit(query.message, "Выбери, что хочешь изменить:", state, reply_markup=kb)
    await query.answer()

# ===================================================
# Клавиатура с выбором поля для изменения peer
# ===================================================
@router.callback_query(F.data.startswith("edit_field:"))
async def peer_edit_field_selected(query: CallbackQuery, state: FSMContext):
    """
    Выбор конкретного поля peer для редактирования.
    Формат callback_data: edit_field:<iface>:<short_id>:<field>
    """
    parts = query.data.split(":", 3)
    if len(parts) < 4:
        await query.answer("Некорректные данные", show_alert=True)
        return

    _, iface, peer_short, field = parts

    data = await state.get_data()
    peers_cache = data.get("peers_cache") or []
    peer_id = next((p["id"] for p in peers_cache if p["short"] == peer_short), None)

    peer = next((p for p in get_peers(iface) if p.get("id") == peer_id), None)
    current_value = peer.get(field) if peer and peer.get(field) is not None else "(пусто)"

    await state.update_data(
        edit_field=field, old_value=current_value,
        iface=iface, peer_id=peer_id, peer_short=peer_short
    )
    await state.set_state(PeerEditStates.waiting_value)

    text = (
        f"Введите новое значение для *{field}*.\n"
        f"Текущее: `{current_value}`"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Отмена", callback_data=f"peerinfo:{iface}:{peer_short}")]
    ])

    # редактируем существующее сообщение, а не создаём новое
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await query.answer()


# ===================================================
# Введение нового значения peer
# ===================================================
@router.message(PeerEditStates.waiting_value)
async def peer_edit_get_value(message: Message, state: FSMContext):
    new_value = message.text.strip()
    data = await state.get_data()
    field = data.get("edit_field")
    old_value = data.get("old_value")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="edit_confirm_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="edit_confirm_no")
        ]
    ])

    text = (
        f"Изменить `{field}`:\n"
        f"• Было: `{old_value}`\n"
        f"• Стало: `{new_value}`"
    )

    await state.update_data(new_value=new_value)
    await state.set_state(PeerEditStates.confirm_change)

    #  редактируем предыдущее «Введите новое значение ...»
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ===================================================
# Подтверждение изменения peer
# ===================================================
@router.callback_query(F.data == "edit_confirm_yes")
async def peer_edit_confirm_yes(query: CallbackQuery, state: FSMContext):
    """
    Применяет изменение peer:
    - подтягивает текущее состояние peer
    - определяет тип поля (число, строка)
    - преобразует введённое значение к нужному типу
    - отправляет полный updatePeerSettings
    """
    data = await state.get_data()
    iface = data.get("iface")
    peer_id = data.get("peer_id")
    field = data.get("edit_field")
    new_value = data.get("new_value")

    if not iface:
        logger.warning("[VPN] iface отсутствует при попытке изменения peer")
        await query.answer("Ошибка: iface отсутствует", show_alert=True)
        await state.clear()
        return

    FIELD_TYPES = {
        "DNS": str,
        "allowed_ip": str,
        "endpoint_allowed_ip": str,
        "name": str,
        "preshared_key": str,
        "private_key": str,
        "keepalive": int,
        "mtu": int,
    }

    try:
        peers = get_peers(iface)
        peer = next((p for p in peers if p.get("id") == peer_id), None)
        if not peer:
            logger.warning(f"[VPN] Peer {peer_id} не найден в {iface}")
            await query.answer("Peer не найден", show_alert=True)
            await state.clear()
            return

        old_value = peer.get(field)
        logger.info(f"[VPN] Изменение peer {peer.get('name')} ({peer_id}) в {iface}: "
                    f"{field}: '{old_value}' → '{new_value}'")

        update_payload = {
            "id": peer_id,
            "DNS": peer.get("DNS", ""),
            "allowed_ip": peer.get("allowed_ip", ""),
            "endpoint_allowed_ip": peer.get("endpoint_allowed_ip", ""),
            "keepalive": peer.get("keepalive", 0),
            "mtu": peer.get("mtu", 1420),
            "name": peer.get("name", ""),
            "preshared_key": peer.get("preshared_key", ""),
            "private_key": peer.get("private_key", "")
        }

        expected_type = FIELD_TYPES.get(field, str)
        if expected_type is int:
            try:
                update_payload[field] = int(new_value)
            except ValueError:
                logger.warning(f"[VPN] Некорректное значение '{new_value}' для поля {field} (ожидалось число)")
                await query.answer(f"Поле {field} должно быть числом", show_alert=True)
                return
        else:
            update_payload[field] = str(new_value)

        logger.debug(f"[VPN] updatePeerSettings/{iface} payload={update_payload}")
        result = wg_request(f"/api/updatePeerSettings/{iface}", "POST", update_payload)
        logger.debug(f"[VPN] Результат обновления peer: {result}")

        if not result.get("status"):
            raise RuntimeError(result.get("message") or "WGDashboard вернул status=False")

        logger.info(f"[VPN] Peer {peer.get('name')} ({peer_id}) успешно обновлён.")
        await query.answer("✅ Изменения применены", show_alert=False)

    except Exception as e:
        logger.exception(f"[VPN] Ошибка при обновлении peer {peer_id} в {iface}: {e}")
        await query.answer(f"⚠️ Ошибка: {e}", show_alert=True)
        return

    await state.clear()
    await show_peers(query.message, iface, state)


@router.callback_query(F.data == "edit_confirm_no")
async def peer_edit_confirm_no(query: CallbackQuery, state: FSMContext):
    """Отмена изменения peer."""
    data = await state.get_data()
    iface = data.get("iface")
    peer_short = data.get("peer_short")

    if not iface or not peer_short:
        logger.warning("[VPN] Отмена изменения peer: отсутствуют iface или peer_short")
        await query.answer("Ошибка: данные не найдены", show_alert=True)
        return

    logger.info(f"[VPN] Изменение peer (iface={iface}, short={peer_short}) отменено пользователем")

    await query.answer("Отменено", show_alert=False)
    for k in ("edit_field", "new_value", "old_value", "peer_id"):
        data.pop(k, None)
    await state.update_data(**data)
    await peer_info_from_data(query.message, iface, peer_short, state)



# ===================================================
# Скачать peer
# ===================================================
@router.callback_query(F.data.startswith("peer_download:"))
async def peer_download_callback(query: CallbackQuery, state: FSMContext):
    _, iface, peer_short = query.data.split(":", 2)
    data = await state.get_data()
    peers_cache = data.get("peers_cache") or []

    peer_id = next((p["id"] for p in peers_cache if p["short"] == peer_short), None)
    peer_name = next((p["name"] for p in peers_cache if p["short"] == peer_short), "peer")

    if not peer_id:
        logger.warning(f"[VPN] Скачивание peer: не найден short_id={peer_short} в {iface}")
        await query.answer("Peer не найден", show_alert=True)
        return

    logger.info(f"[VPN] Скачивание конфигурации peer {peer_name} ({peer_id}) из {iface}")
    try:
        filename, content_bytes = download_peer_file(iface, peer_id)
        buffer = io.BytesIO(content_bytes)
        file_to_send = BufferedInputFile(buffer.getvalue(), filename=f"{filename}.conf")

        await query.message.answer_document(
            document=file_to_send,
            caption=f"📄 Конфигурация для *{peer_name}*",
            parse_mode="Markdown"
        )
        logger.info(f"[VPN] Конфиг {filename}.conf для peer {peer_name} отправлен пользователю")
        await query.answer("Файл отправлен ✅", show_alert=False)

    except Exception as e:
        logger.exception(f"[VPN] Ошибка при скачивании файла peer {peer_name} ({peer_id}): {e}")
        await query.answer(f"⚠️ Ошибка загрузки: {e}", show_alert=True)


# ===================================================
# Скачать все пиры интерфейса в архиве
# ===================================================
@router.callback_query(F.data.startswith("download_all:"))
async def download_all_peers_callback(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    logger.info(f"[VPN] Запрошено скачивание архива всех peer для {iface}")
    try:
        filename, zip_bytes = download_all_peers_zip(iface)
        file_to_send = BufferedInputFile(zip_bytes, filename=filename)

        await query.message.answer_document(
            document=file_to_send,
            caption=f"📦 Архив всех конфигов для *{iface}*",
            parse_mode="Markdown"
        )
        logger.info(f"[VPN] Архив {filename} успешно отправлен пользователю")
        await query.answer("Архив отправлен ✅", show_alert=False)
    except Exception as e:
        logger.exception(f"[VPN] Ошибка при скачивании архива peer для {iface}: {e}")
        await query.answer(f"⚠️ Ошибка: {e}", show_alert=True)


# ===================================================
# Удаление интерфейса
# ===================================================
@router.callback_query(F.data.startswith("del_config:"))
async def config_delete_confirm(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    logger.info(f"[VPN] Пользователь запросил удаление конфигурации {iface}")

    text = f"❗ Вы уверены, что хотите удалить конфигурацию *{iface}* ?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"del_config_yes:{iface}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"iface:{iface}")
        ]
    ])
    await _send_or_edit(query.message, text, state,
                        parse_mode="Markdown", reply_markup=kb)
    await query.answer()


# ===================================================
# Подтверждение удаления интерфейса
# ===================================================
@router.callback_query(F.data.startswith("del_config_yes:"))
async def config_delete_yes(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    ok, msg = delete_wireguard_config(iface)
    if ok:
        text = f"🗑 Конфигурация *{iface}* успешно удалена."
    else:
        text = f"⚠️ Ошибка при удалении *{iface}*:\n```\n{msg or 'Неизвестная ошибка'}\n```"
    await _send_or_edit(query.message, text, state,
                        parse_mode="Markdown")
    await show_interfaces(query.message, state)


# ===================================================
# Переключение интерфейса
# ===================================================
@router.callback_query(F.data.startswith("toggle_iface:"))
async def iface_toggle(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    try:
        logger.info(f"[VPN] Переключение интерфейса {iface}...")
        new_state, ok = toggle_config(iface)
        if ok:
            human_state = "включён" if new_state else "выключен"
            logger.info(f"[VPN] Интерфейс {iface} успешно {human_state}")
            text = "🟢 Интерфейс включён" if new_state else "🔴 Интерфейс выключен"
            await query.answer(text, show_alert=False)
        else:
            logger.warning(f"[VPN] WGDashboard вернул status=False при переключении {iface}")
            await query.answer("⚠️ Не удалось переключить интерфейс", show_alert=True)
    except Exception as e:
        logger.exception(f"[VPN] Ошибка при переключении интерфейса {iface}: {e}")
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return

    await show_peers(query.message, iface, state)


# ===================================================
# Добавление конфигурации
# ===================================================
@router.callback_query(F.data == "add_config")
async def add_config_start(query: CallbackQuery, state: FSMContext):
    example = (
        "Введите данные новой конфигурации **в формате JSON**:\n"
        "```\n"
        "{\n"
        '  "ConfigurationName": "wg1",\n'
        '  "Address": "10.70.1.1/24",\n'
        '  "ListenPort": 51801\n'
        "}\n"
        "```"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Отменить", callback_data="back_main")]
    ])
    await _send_or_edit(query.message, example, state,
                        parse_mode="Markdown", reply_markup=kb)
    await state.set_state(AddConfigStates.waiting_json)
    await query.answer()


@router.message(AddConfigStates.waiting_json)
async def add_config_process(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`").strip()
    try:
        payload = json.loads(text)
        logger.info(f"[VPN] Запрошено создание конфигурации: {payload}")
    except Exception as e:
        logger.exception("[VPN] Ошибка чтения JSON при создании конфигурации")
        await message.answer(f"❌ Ошибка чтения JSON:\n```\n{e}\n```", parse_mode="Markdown")
        await show_interfaces(message, state, force_new=True)
        await state.clear()
        return

    try:
        if not payload.get("PrivateKey"):
            payload["PrivateKey"] = generate_private_key()
            logger.debug(f"[VPN] PrivateKey для {payload.get('ConfigurationName')} сгенерирован автоматически")

        if not payload.get("Protocol"):
            payload["Protocol"] = "wg"

        ok, msg = add_wireguard_config(payload)
        if ok:
            logger.info(f"[VPN] Конфигурация {payload.get('ConfigurationName')} успешно создана.")
            await message.answer("✅ Конфигурация успешно создана.")
        else:
            logger.error(f"[VPN] Ошибка создания конфигурации {payload.get('ConfigurationName')}: {msg}")
            await message.answer(f"⚠️ Ошибка создания:\n```\n{msg or 'Неизвестная ошибка'}\n```",
                                 parse_mode="Markdown")
    except Exception as e:
        logger.exception(f"[VPN] Исключение при создании конфигурации: {e}")
        await message.answer(f"⚠️ Ошибка создания конфигурации:\n```\n{e}\n```",
                             parse_mode="Markdown")

    await show_interfaces(message, state, force_new=True)
    await state.clear()


# ===================================================
# Удаление конфигурации
# ===================================================
@router.callback_query(F.data.startswith("del_config:"))
async def config_delete_confirm(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    text = f"❗ Удалить конфигурацию *{iface}*?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"del_config_yes:{iface}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"iface:{iface}")
        ]
    ])
    await _send_or_edit(query.message, text, state,
                        parse_mode="Markdown", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("del_config_yes:"))
async def config_delete_yes(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    try:
        logger.info(f"[VPN] Удаление конфигурации {iface} запущено")
        ok, msg = delete_wireguard_config(iface)
        if ok:
            logger.info(f"[VPN] Конфигурация {iface} успешно удалена")
            text = f"🗑 Конфигурация *{iface}* успешно удалена."
        else:
            logger.error(f"[VPN] Ошибка удаления конфигурации {iface}: {msg}")
            text = f"⚠️ Ошибка при удалении *{iface}*:\n```\n{msg or 'Неизвестная ошибка'}\n```"
    except Exception as e:
        logger.exception(f"[VPN] Исключение при удалении конфигурации {iface}: {e}")
        text = f"❌ Ошибка удаления:\n```\n{e}\n```"

    await _send_or_edit(query.message, text, state, parse_mode="Markdown")
    await show_interfaces(query.message, state)


# ===================================================
# Обновление и возврат
# ===================================================
@router.callback_query(F.data.startswith("refresh:"))
async def refresh_iface(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    await show_peers(query.message, iface, state)
    await query.answer("Обновлено")


@router.callback_query(F.data == "back_main")
async def back_main(query: CallbackQuery, state: FSMContext):
    await show_interfaces(query.message, state)
    await state.update_data(peers_cache=[])
    await query.answer()


def _bottom_menu(iface: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить", callback_data="peer_add"),
            InlineKeyboardButton(text="🔁 Обновить", callback_data=f"refresh:{iface}")
        ],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back_main")]
    ])