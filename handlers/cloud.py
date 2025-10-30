import os
import traceback
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from typing import Dict, Optional

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from logger.logger import logger

load_dotenv()

router = Router()

CONFIG = {
    'base_url': os.getenv('base_url'),
    'tenant': os.getenv('tenant'),
    'refresh_token': os.getenv('refresh_token'),
    'org_urn': os.getenv('org_urn'),
    'vdc_id': os.getenv('vdc_id'),
    'storage_gold_urn': os.getenv('storage_gold_urn'),
    'storage_bronze_urn': os.getenv('storage_bronze_urn'),
}


# === BASE HELPERS ===
def get_bearer_token() -> Optional[str]:
    """Получает временный Bearer‑токен."""
    url = f"{CONFIG['base_url']}/oauth/tenant/{CONFIG['tenant']}/token"
    headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "refresh_token", "refresh_token": CONFIG["refresh_token"]}
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ValueError(f"access_token отсутствует: {response.text}")
        logger.info("Bearer токен успешно получен")
        return token
    except Exception as e:
        logger.error(f"Ошибка при получении Bearer токена: {e}\n{traceback.format_exc()}")
        return None


def make_api_call(url: str, headers: dict) -> Optional[dict]:
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"Ошибка при GET {url}: {e}\n{traceback.format_exc()}")
        return None


def get_storage_usage(storage_policy_urn: str, policy_name: str, token: str) -> Optional[Dict]:
    total_used = 0
    page = 1
    while True:
        url = (f"{CONFIG['base_url']}/cloudapi/1.0.0/orgVdcStoragePolicies/"
               f"{storage_policy_urn}/consumers?page={page}&pageSize=25")
        headers = {"accept": "application/json;version=39.1", "Authorization": f"Bearer {token}"}
        data = make_api_call(url, headers)
        if not data or 'values' not in data:
            break
        total_used += sum(x['storageConsumedMb'] for x in data['values'])
        if page >= data.get('pageCount', 1):
            break
        page += 1
    return {'policy_name': policy_name, 'total_used': total_used}


def get_vdc_resources(token: str) -> Optional[dict]:
    try:
        url = f"{CONFIG['base_url']}/api/vdc/{CONFIG['vdc_id']}"
        headers = {"accept": "application/*;version=39.1", "Authorization": f"Bearer {token}"}
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {'vcloud': 'http://www.vmware.com/vcloud/v1.5'}
        cpu_elem = root.find('.//vcloud:Cpu', ns)
        mem_elem = root.find('.//vcloud:Memory', ns)
        cpu_alloc = int(cpu_elem.find('vcloud:Allocated', ns).text)
        cpu_used = int(cpu_elem.find('vcloud:Used', ns).text)
        mem_alloc = int(mem_elem.find('vcloud:Allocated', ns).text)
        mem_used = int(mem_elem.find('vcloud:Used', ns).text)
        return {
            'cpu_allocated': cpu_alloc,
            'cpu_used': cpu_used,
            'memory_allocated': mem_alloc,
            'memory_used': mem_used
        }
    except Exception as e:
        logger.error(f"Ошибка при получении VDC: {e}\n{traceback.format_exc()}")
        return None


def get_storage_limits(token: str) -> Optional[dict]:
    headers = {"accept": "application/json;version=39.1", "Authorization": f"Bearer {token}"}
    try:
        gold = make_api_call(f"{CONFIG['base_url']}/cloudapi/1.0.0/orgVdcStoragePolicies/{CONFIG['storage_gold_urn']}", headers)
        bronze = make_api_call(f"{CONFIG['base_url']}/cloudapi/1.0.0/orgVdcStoragePolicies/{CONFIG['storage_bronze_urn']}", headers)
        return {
            'gold_limit': gold.get('storageLimitMb', 0) if gold else 0,
            'bronze_limit': bronze.get('storageLimitMb', 0) if bronze else 0
        }
    except Exception as e:
        logger.error(f"Ошибка при лимитах хранилища: {e}\n{traceback.format_exc()}")
        return None


# === FORMAT ===
def fmt_storage(mb: int) -> str:
    if mb >= 1024 * 1024:
        return f"{mb / (1024 * 1024):.1f} TB"
    elif mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb} MB"


def fmt_mem(mb: int) -> str:
    return f"{mb / 1024:.0f} GB" if mb >= 1024 else f"{mb} MB"


def fmt_cpu(mhz: int) -> tuple:
    ghz = mhz / 1000
    cores = ghz * 1.73
    return ghz, cores


# === INLINE KEYBOARDS ===
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Диск", callback_data="cloud_disk"),
         InlineKeyboardButton(text="🧠 RAM", callback_data="cloud_ram")],
        [InlineKeyboardButton(text="⚙️ CPU", callback_data="cloud_cpu"),
         InlineKeyboardButton(text="📊 Все ресурсы", callback_data="cloud_all")],
    ])


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="cloud_back"),
         InlineKeyboardButton(text="🔁 Повторить", callback_data="cloud_repeat")]
    ])


# === HANDLERS ===
@router.message(Command("cloudinfo"))
async def cmd_cloudinfo(message: types.Message):
    logger.info(f"Пользователь {message.from_user.id} вызвал /cloudinfo")
    await message.answer("Выберите интересующий ресурс ☁️", reply_markup=main_menu())


async def compose_report(token: str, section: str) -> str:
    limits = get_storage_limits(token)
    bronze = get_storage_usage(CONFIG['storage_bronze_urn'], "Bronze", token)
    gold = get_storage_usage(CONFIG['storage_gold_urn'], "Gold", token)
    vdc = get_vdc_resources(token)

    if not all([limits, bronze, gold, vdc]):
        return "⚠️ Ошибка при получении данных."

    def percent(used, total): return (used / total * 100) if total else 0

    # Расычитанные значения
    bronze_rem = limits['bronze_limit'] - bronze['total_used']
    gold_rem = limits['gold_limit'] - gold['total_used']
    cpu_rem = vdc['cpu_allocated'] - vdc['cpu_used']
    mem_rem = vdc['memory_allocated'] - vdc['memory_used']

    cpu_used_ghz, cpu_used_cores = fmt_cpu(vdc['cpu_used'])
    cpu_alloc_ghz, cpu_alloc_cores = fmt_cpu(vdc['cpu_allocated'])
    cpu_rem_ghz, cpu_rem_cores = fmt_cpu(cpu_rem)

    text_lines = []

    if section in ("disk", "all"):
        for name, usage, limit, rem in [
            ("🟤 BRONZE STORAGE", bronze['total_used'], limits['bronze_limit'], bronze_rem),
            ("🟡 GOLD STORAGE", gold['total_used'], limits['gold_limit'], gold_rem),
        ]:
            perc = percent(usage, limit)
            text_lines += [
                f"{name}:",
                f"   Использовано: {fmt_storage(usage)} из {fmt_storage(limit)}",
                f"   Заполнение: {perc:.1f}%",
                f"   Остаток: {fmt_storage(rem)}",
                ""
            ]

    if section in ("ram", "all"):
        perc = percent(vdc['memory_used'], vdc['memory_allocated'])
        text_lines += [
            "🧠 <b>RAM</b>",
            f"   Использовано: {fmt_mem(vdc['memory_used'])} из {fmt_mem(vdc['memory_allocated'])}",
            f"   Заполнение: {perc:.1f}%",
            f"   Остаток: {fmt_mem(mem_rem)}",
            ""
        ]

    if section in ("cpu", "all"):
        perc = percent(vdc['cpu_used'], vdc['cpu_allocated'])
        text_lines += [
            "⚙️ <b>CPU</b>",
            f"   Использовано: {cpu_used_ghz:.0f} GHz ({cpu_used_cores:.0f} ядер) из {cpu_alloc_ghz:.0f} GHz ({cpu_alloc_cores:.0f} ядер)",
            f"   Заполнение: {perc:.1f}%",
            f"   Остаток: {cpu_rem_ghz:.0f} GHz ({cpu_rem_cores:.0f} ядер)",
            ""
        ]

    return "\n".join(text_lines)


@router.callback_query(F.data.startswith("cloud_"))
async def callback_cloud(query: types.CallbackQuery):
    action = query.data.split("_")[1]
    user_id = query.from_user.id
    logger.info(f"Пользователь {user_id} нажал {action}")

    if action == "back":
        await query.message.edit_text("Выберите интересующий ресурс ☁️", reply_markup=main_menu())
        return

    if action == "repeat":
        # Повторим предыдущий (из caption? здесь просто перезапрос "все")
        action = "all"

    token = get_bearer_token()
    if not token:
        await query.message.edit_text("🚫 Не удалось авторизоваться в облаке.", reply_markup=main_menu())
        return

    try:
        # Уберём старое меню
        await query.message.delete()

        text = await compose_report(token, action)
        await query.message.answer(text, parse_mode="HTML", reply_markup=back_menu())
    except Exception as e:
        logger.error(f"Ошибка при cloud_{action}: {e}\n{traceback.format_exc()}")
        await query.message.answer("❌ Произошла ошибка при получении данных.", reply_markup=main_menu())