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


# ===================================================
# Настройки WGDashboard API
# ===================================================
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

router = Router()


# ===================================================
# Вспомогательные функции для REST
# ===================================================
def wg_request(endpoint, method="GET", payload=None):
    headers = {"wg-dashboard-apikey": API_KEY, "Content-Type": "application/json"}
    url = f"{API_URL}{endpoint}"
    r = requests.request(method, url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def get_interfaces():
    resp = wg_request("/api/getWireguardConfigurations")
    return resp.get("data", [])


def get_peers(config_name: str):
    resp = wg_request(f"/api/getWireguardConfigurationInfo?configurationName={config_name}")
    data = resp.get("data", {})
    return data.get("configurationPeers", [])


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
@router.message(F.text == "/vpn")
async def cmd_vpn(message: Message, state: FSMContext):
    await show_interfaces(message, state, force_new=True)


async def show_interfaces(target, state: FSMContext, force_new=False):
    try:
        configs = get_interfaces()
    except Exception as e:
        await _send_or_edit(
            target, f"❌ Ошибка получения конфигураций:\n```\n{e}\n```",
            state, parse_mode="Markdown", force_new=True
        )
        return

    if not configs:
        await _send_or_edit(target, "Нет доступных интерфейсов.", state, force_new=True)
        return

    inline = []
    for cfg in configs:
        status = "🟢" if cfg.get("Status") else "🔴"
        name = cfg.get("Name", "unknown")
        inline.append([InlineKeyboardButton(text=f"{status} {name}",
                                            callback_data=f"iface:{name}")])

    inline.append([
        InlineKeyboardButton(text="➕ Добавить конфигурацию",
                             callback_data="add_config")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=inline)
    await _send_or_edit(target, "Выбери конфигурацию:", state,
                        reply_markup=kb, force_new=force_new)


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
    """
    Отображает peers выбранного интерфейса:
    🟢/🔴 статус интерфейса, список peers, действия управления.
    """
    try:
        # Получаем полную информацию о конфигурации
        info = wg_request(f"/api/getWireguardConfigurationInfo?configurationName={iface}")
        conf_info = info.get("data", {}).get("configurationInfo", {})
        iface_enabled = bool(conf_info.get("Status"))
        iface_status = "🟢" if iface_enabled else "🔴"
        peers = info.get("data", {}).get("configurationPeers", [])
    except Exception as e:
        await _send_or_edit(
            message, f"❌ Ошибка загрузки peers:\n```\n{e}\n```",
            state, parse_mode="Markdown"
        )
        return

    # ===================== peers =====================
    buttons, row = [], []
    short_cache = []
    for p in peers:
        name = (p.get("name") or "(без имени)")[:20]
        pid = p["id"]
        status_dot = "🟢" if p.get("status") == "running" else "🔴"
        label = f"{status_dot} {name}"
        short_cache.append({"id": pid, "name": name})
        row.append(InlineKeyboardButton(text=label, callback_data=f"peerinfo:{pid}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # ===================== actions =====================
    # power toggle
    toggle_text = "🟥 Выключить интерфейс" if iface_enabled else "🟩 Включить интерфейс"

    # верхняя строка кнопок
    buttons.append([
        InlineKeyboardButton(text="📦 Скачать все конфиги",
                             callback_data=f"download_all:{iface}"),
        InlineKeyboardButton(text=toggle_text,
                             callback_data=f"toggle_iface:{iface}")
    ])

    # нижняя строка управления
    buttons.append([
        InlineKeyboardButton(text="🗑 Удалить конфигурацию",
                             callback_data=f"del_config:{iface}")
    ])

    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh:{iface}"),
        InlineKeyboardButton(text="➕ Добавить peer", callback_data="peer_add"),
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="back_main")
    ])

    # ----------------- отрисовываем меню -----------------
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    header = f"{iface_status} *{iface}* — список peer'ов:"
    await _send_or_edit(message, header, state, parse_mode="Markdown", reply_markup=kb)

    # сохраняем peers для последующего обращения
    await state.update_data(peers_cache=short_cache)


# ===================================================
# Карточка peer + удаление
# ===================================================
@router.callback_query(F.data.startswith("peerinfo:"))
async def peer_info(query: CallbackQuery, state: FSMContext):
    """
    Карточка конкретного peer: показывает информацию,
    и добавляет кнопки 📥 Скачать, 🗑 Удалить, ⬅ Назад.
    """
    peer_id = query.data.split(":", 1)[1]
    data = await state.get_data()
    iface = data.get("interface")
    peers_cache = data.get("peers_cache") or []

    # ищем peer в кеше и по API
    peer_name = next((p["name"] for p in peers_cache if p["id"] == peer_id), None)
    peer = next((p for p in get_peers(iface) if p.get("id") == peer_id), None)
    if not peer:
        await query.answer("Peer не найден", show_alert=True)
        return

    name = peer.get("name") or peer_name or "(без имени)"
    lines = [
        f"*Peer — {name}*",
        f"• Public Key: `{peer.get('id')}`",
        f"• Allowed IPs: `{peer.get('allowed_ip')}`",
        f"• Endpoint Allowed IPs: `{peer.get('endpoint_allowed_ip')}`",
        f"• DNS: `{peer.get('DNS')}`",
        f"• Pre-Shared Key: `{peer.get('preshared_key')}`",
        f"• MTU: `{peer.get('mtu')}`",
        f"• Keepalive: `{peer.get('keepalive')}`",
        f"• Status: {'🟢 running' if peer.get('status') == 'running' else '⚫️ stopped'}",
        f"• Last handshake: `{peer.get('latest_handshake')}`",
        f"• Traffic: ↓{peer.get('total_receive')} / ↑{peer.get('total_sent')} GB",
    ]
    text = "\n".join(lines)

    # ===== КНОПКИ под карточкой =====
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [   # кнопка скачать файл peer
            InlineKeyboardButton(
                text="📥 Скачать файл",
                callback_data=f"peer_download:{peer_id}"
            ),
        ],
        [   # кнопка удалить peer
            InlineKeyboardButton(
                text="🗑 Удалить peer",
                callback_data=f"peer_delask:{peer_id}"
            ),
        ],
        [   # кнопка назад
            InlineKeyboardButton(
                text="⬅ Назад",
                callback_data=f"iface:{iface}"
            ),
        ],
    ])

    await _send_or_edit(query.message, text, state,
                        parse_mode="Markdown", reply_markup=kb)
    await query.answer()


# ========== подтверждение удаления ==========
@router.callback_query(F.data.startswith("peer_delask:"))
async def peer_delete_confirm(query: CallbackQuery, state: FSMContext):
    peer_id = query.data.split(":", 1)[1]
    data = await state.get_data()
    iface = data.get("interface")
    peers_cache = data.get("peers_cache") or []
    peer_name = next((p["name"] for p in peers_cache if p["id"] == peer_id), "(без имени)")

    text = f"❗ Удалить peer *{peer_name}* из *{iface}*?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"peer_delyes:{peer_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"peerinfo:{peer_id}")
        ]
    ])
    await _send_or_edit(query.message, text, state,
                        parse_mode="Markdown", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("peer_delyes:"))
async def peer_delete_yes(query: CallbackQuery, state: FSMContext):
    peer_id = query.data.split(":", 1)[1]
    data = await state.get_data()
    iface = data.get("interface")
    peers_cache = data.get("peers_cache") or []
    name = next((p["name"] for p in peers_cache if p["id"] == peer_id), "(без имени)")

    try:
        if delete_peer(iface, peer_id):
            msg = f"❌ Peer *{name}* удалён из `{iface}`"
        else:
            msg = f"⚠️ Не удалось удалить peer *{name}*"
    except Exception as e:
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
        peer_id = create_peer(iface, peer_name)
        await message.answer(
            f"✅ Peer *{peer_name}* создан в `{iface}`\nPublic key: `{peer_id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка создания peer:\n```\n{e}\n```",
                             parse_mode="Markdown")
    await show_peers(message, iface, state)


# ===================================================
# Скачать peer
# ===================================================
@router.callback_query(F.data.startswith("peer_download:"))
async def peer_download_callback(query: CallbackQuery, state: FSMContext):
    """
    Скачивает peer‑конфигурацию и отправляет пользователю .conf файл напрямую из памяти.
    """
    peer_id = query.data.split(":", 1)[1]
    data = await state.get_data()
    iface = data.get("interface")
    peers_cache = data.get("peers_cache") or []
    peer_name = next((p["name"] for p in peers_cache if p["id"] == peer_id), "peer")

    try:
        # загружаем файл из WGDashboard API
        filename, content_bytes = download_peer_file(iface, peer_id)
        buffer = io.BytesIO(content_bytes)
        buffer.name = f"{filename}.conf"

        # aiogram 3 использует BufferedInputFile для отправки из памяти
        file_to_send = BufferedInputFile(buffer.getvalue(), filename=f"{filename}.conf")

        await query.message.answer_document(
            document=file_to_send,
            caption=f"📄 Конфигурация для *{peer_name}*",
            parse_mode="Markdown"
        )

        await query.answer("Файл отправлен ✅", show_alert=False)

    except Exception as e:
        await query.answer(f"⚠️ Ошибка загрузки: {e}", show_alert=True)


# ===================================================
# Скачать все пиры интерфейса в архиве
# ===================================================
@router.callback_query(F.data.startswith("download_all:"))
async def download_all_peers_callback(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    try:
        filename, zip_bytes = download_all_peers_zip(iface)
        file_to_send = BufferedInputFile(zip_bytes, filename=filename)
        await query.message.answer_document(
            document=file_to_send,
            caption=f"📦 Архив всех конфигов для *{iface}*",
            parse_mode="Markdown"
        )
        await query.answer("Архив отправлен ✅", show_alert=False)
    except Exception as e:
        await query.answer(f"⚠️ Ошибка: {e}", show_alert=True)


# ===================================================
# Удаление интерфейса
# ===================================================
@router.callback_query(F.data.startswith("del_config:"))
async def config_delete_confirm(query: CallbackQuery, state: FSMContext):
    iface = query.data.split(":", 1)[1]
    text = f"❗ Вы уверены, что хотите удалить конфигурацию *{iface}* ?"
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
        new_state, ok = toggle_config(iface)
        if ok:
            text = "🟢 Интерфейс включён" if new_state else "🔴 Интерфейс выключен"
            await query.answer(text, show_alert=False)
        else:
            await query.answer("⚠️ Не удалось переключить интерфейс", show_alert=True)
    except Exception as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return

    # после переключения обновляем экран
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
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения JSON:\n```\n{e}\n```", parse_mode="Markdown")
        await show_interfaces(message, state, force_new=True)
        await state.clear()
        return

    # ── Добавляем недостающие поля ──
    if not payload.get("PrivateKey"):
        try:
            payload["PrivateKey"] = generate_private_key()
            await message.answer("🔑 Private key сгенерирован автоматически.")
        except Exception as e:
            await message.answer(f"⚠️ Не удалось сгенерировать ключ:\n```\n{e}\n```",
                                 parse_mode="Markdown")
            await show_interfaces(message, state, force_new=True)
            await state.clear()
            return

    if not payload.get("Protocol"):
        payload["Protocol"] = "wg"

    # создаём конфигурацию
    ok, msg = add_wireguard_config(payload)
    if ok:
        await message.answer("✅ Конфигурация успешно создана.")
    else:
        await message.answer(f"⚠️ Ошибка создания:\n```\n{msg or 'Неизвестная ошибка'}\n```",
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
    ok, msg = delete_wireguard_config(iface)
    if ok:
        text = f"🗑 Конфигурация *{iface}* успешно удалена."
    else:
        text = f"⚠️ Ошибка удаления:\n```\n{msg or 'Неизвестная ошибка'}\n```"
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