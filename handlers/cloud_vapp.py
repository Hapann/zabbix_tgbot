#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import math
import requests
import time
import xml.etree.ElementTree as ET
import pandas as pd
import io
import textwrap
from dotenv import load_dotenv
from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from logger.logger import logger
from datetime import datetime, timedelta


# ------------------------------------------------------------------------------
# ROUTER
# ------------------------------------------------------------------------------
router = Router(name=__name__)
requests.packages.urllib3.disable_warnings()
load_dotenv()


# --- кэш ---
TOKEN_CACHE = {"token": None, "time": None}
VAPP_CACHE = {"data": None, "time": None}

TOKEN_TTL = 55 * 60       # 55 минут
VAPP_TTL = 5 * 60         # 5 минут (через 5 мин обновим список)


# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
CONFIG = {
    "base_url": os.getenv("base_url"),
    "tenant": os.getenv("tenant"),
    "refresh_token": os.getenv("refresh_token"),
    "vdc_id": os.getenv("vdc_id"),
    "storage_gold_urn": os.getenv("storage_gold_urn"),
    "storage_bronze_urn": os.getenv("storage_bronze_urn"),
}
API_VERSION = "40.0.0-alpha"


# ------------------------------------------------------------------------------
# CLOUD UTILS
# ------------------------------------------------------------------------------
def get_bearer_token(cfg: dict) -> str:
    """Получаем или возвращаем из кэша Bearer‑токен"""
    # если есть токен и он не устарел
    if TOKEN_CACHE["token"] and TOKEN_CACHE["time"]:
        elapsed = time.time() - TOKEN_CACHE["time"]
        if elapsed < TOKEN_TTL:
            logger.debug("♻️ Используем кэшированный Bearer‑токен")
            return TOKEN_CACHE["token"]

    # иначе запрашиваем новый
    url = f"{cfg['base_url']}/oauth/tenant/{cfg['tenant']}/token"
    headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "refresh_token", "refresh_token": cfg["refresh_token"]}
    try:
        r = requests.post(url, headers=headers, data=data, verify=False, timeout=20)
        r.raise_for_status()
        token = r.json().get("access_token")
        if not token:
            raise RuntimeError("Пустой access_token")
        TOKEN_CACHE["token"] = token
        TOKEN_CACHE["time"] = time.time()
        logger.info("✅ Обновлён Bearer‑токен и сохранён в кэш")
        return token
    except Exception as e:
        logger.exception(f"Ошибка при обновлении токена: {e}")
        raise


def get_vapps(cfg, token, force_update=False) -> pd.DataFrame:
    """
    Возвращает список vApp с ресурсами и цветным статусом (для клавиатуры).
    """
    start = time.time()
    logger.info("🚀 Запрос списка vApp (ресурсы + статусы)")

    if (
        not force_update
        and VAPP_CACHE["data"] is not None
        and VAPP_CACHE["time"]
        and (time.time() - VAPP_CACHE["time"] < VAPP_TTL)
    ):
        logger.info("♻️ Использован кэш")
        return VAPP_CACHE["data"]

    try:
        params = {
            "type": "vApp", "format": "records",
            "page": 1, "pageSize": 200,
            "filterEncoded": "true",
            "filter": f"(vdc=={cfg['vdc_id']})"
        }
        headers = {
            "Accept": "application/*+xml;version=40.0.0-alpha",
            "Authorization": f"Bearer {token}"
        }

        r = requests.get(f"{cfg['base_url']}/api/query",
                         headers=headers, params=params, verify=False)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = {"v": "http://www.vmware.com/vcloud/v1.5"}

        data = []
        for rec in root.findall("v:VAppRecord", ns):
            name = rec.attrib.get("name", "—")

            # сначала читаем статус
            raw_state = rec.attrib.get("status", "").upper().strip()
            logger.debug(f"vApp {name} → status='{raw_state}'")

            # подставляем цвет
            if "POWERED_ON" in raw_state or raw_state == "ON":
                indicator = "🟢"
            elif "POWERED_OFF" in raw_state or raw_state == "OFF":
                indicator = "🔴"
            elif "MIX" in raw_state or "RESOLVED" in raw_state or "PART" in raw_state:
                indicator = "🟡"
            else:
                indicator = "⚪"

            href = rec.attrib.get("href", "")
            cpus = int(rec.attrib.get("numberOfCpus", 0))
            ram_mb = int(rec.attrib.get("memoryAllocationMB", 0))
            storage_mb = int(rec.attrib.get("totalStorageAllocatedMb",
                            int(rec.attrib.get("storageKB", 0)) / 1024))

            data.append({
                "Статус": indicator,
                "Имя vApp": name,
                "vCPU": cpus,
                "RAM (ГБ)": ram_mb / 1024,
                "Диск (ГБ)": storage_mb / 1024,
                "href": href
            })

        df = pd.DataFrame(data)
        VAPP_CACHE.update({"data": df, "time": time.time()})
        logger.info(f"✅ Получено {len(df)} vApp, {time.time()-start:.2f}s")
        return df

    except Exception as e:
        logger.exception(f"❌ Ошибка получения vApp: {e}")
        return pd.DataFrame()


def get_storage_limits(cfg, token) -> float:
    """
    Подсчитывает общий лимит Storage (Bronze + Gold) через CloudAPI consumers.
    """
    def collect_used(urn):
        page, total = 1, 0
        while True:
            url = (f"{cfg['base_url']}/cloudapi/1.0.0/orgVdcStoragePolicies/"
                   f"{urn}/consumers?page={page}&pageSize=25")
            headers = {
                "Accept": "application/json;version=39.1",
                "Authorization": f"Bearer {token}",
            }
            r = requests.get(url, headers=headers, verify=False)
            if not r.ok:
                break
            js = r.json()
            vals = js.get("values", [])
            total += sum(v.get("storageConsumedMb", 0) for v in vals)
            if page >= js.get("pageCount", 1):
                break
            page += 1
        return total

    try:
        used_bronze = collect_used(cfg["storage_bronze_urn"])
        used_gold = collect_used(cfg["storage_gold_urn"])

        # лимиты
        for urn_type in ("storage_gold_urn", "storage_bronze_urn"):
            url = f"{cfg['base_url']}/cloudapi/1.0.0/orgVdcStoragePolicies/{cfg[urn_type]}"
            hdr = {
                "Accept": "application/json;version=39.1",
                "Authorization": f"Bearer {token}",
            }
            r = requests.get(url, headers=hdr, verify=False)
            if not r.ok:
                raise RuntimeError(f"Storage {urn_type} {r.status_code}")
            limit_mb = r.json().get("storageLimitMb", 0)
            if urn_type.endswith("gold_urn"):
                gold_limit = limit_mb
            else:
                bronze_limit = limit_mb

        total_limit_tb = (gold_limit + bronze_limit) / 1024 / 1024
        total_used_tb = (used_gold + used_bronze) / 1024 / 1024
        logger.info(
            f"✅ Storage лимит: {total_limit_tb:.2f} ТБ, "
            f"использовано {total_used_tb:.2f} ТБ"
        )
        return total_limit_tb
    except Exception as e:
        logger.warning(f"⚠️ Ошибка Storage лимитов: {e}")
        return 0.0


# ------------------------------------------------------------------------------
# клавиатуры
# ------------------------------------------------------------------------------
def keyboard_vapp_list(df: pd.DataFrame, page: int = 1, per_page: int = 12) -> types.InlineKeyboardMarkup:
    """3×4 список vApp с индикацией статуса + пагинация + кнопки общих отчётов."""
    total_pages = max(1, math.ceil(len(df) / per_page))
    page = max(1, min(page, total_pages))
    start, end = (page - 1) * per_page, page * per_page
    subset = df.iloc[start:end]

    kb = InlineKeyboardBuilder()

    # --- основная сетка 3×4 ---
    for _, row in subset.iterrows():
        name = row["Имя vApp"]
        status_icon = row.get("Статус", "⚪")
        kb.button(text=f"{status_icon} {name}", callback_data=f"vapp:{name}")
    kb.adjust(3)

    # --- пагинация ---
    if total_pages > 1:
        left_btn = types.InlineKeyboardButton(
            text="⏮️", callback_data=f"page:{page-1}" if page > 1 else "noop")
        counter_btn = types.InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop")
        right_btn = types.InlineKeyboardButton(
            text="⏭️", callback_data=f"page:{page+1}" if page < total_pages else "noop")
        kb.row(left_btn, counter_btn, right_btn)

    # --- нижние кнопки ---
    kb.row(
        # Кнопка теперь открывает статистику всех vApp и названа PC info
        types.InlineKeyboardButton(text="🖥 PC info (все vApp)", callback_data="vapp:stats"),
    )
    kb.row(
        types.InlineKeyboardButton(text="📄 CSV (все vApp)", callback_data="allvapp_csv"),
        types.InlineKeyboardButton(text="📱 Mobile info (все vApp)", callback_data="allvapp_mobile"),
    )

    return kb.as_markup()

def keyboard_vapp_detail(name: str) -> types.InlineKeyboardMarkup:
    """Карточка vApp: инфо‑режимы + экспорт"""
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back:vapp_list"))
    kb.row(
        types.InlineKeyboardButton(text="🖥 PC info", callback_data=f"vappinfo_pc:{name}"),
        types.InlineKeyboardButton(text="📱 Mobile info", callback_data=f"vappinfo_mobile:{name}")
    )
    kb.row(types.InlineKeyboardButton(text="📄 CSV файл", callback_data=f"vappinfo_csv:{name}"))
    return kb.as_markup()



def summarize_all_vapps(cfg, token) -> str:
    """
    Сводный отчёт по всем vApp.
    """
    try:
        start = time.time()
        logger.info("📊 Расчёт статистики по всем vApp")

        # --- лимиты CPU/RAM ---
        vdc_url = f"{cfg['base_url']}/api/vdc/{cfg['vdc_id']}"
        hdrs = {"Accept": "application/*+xml;version=39.1",
                "Authorization": f"Bearer {token}"}
        r = requests.get(vdc_url, headers=hdrs, verify=False)
        r.raise_for_status()
        ns = {"v": "http://www.vmware.com/vcloud/v1.5"}
        root = ET.fromstring(r.text)
        cpu_vcpu = int(root.find(".//v:Cpu/v:Allocated", ns).text) / 1000 / 1.73
        ram_gb = int(root.find(".//v:Memory/v:Allocated", ns).text) / 1024

        # --- storage limit & usage (CloudAPI /consumers)
        def get_storage_totals():
            heads = {"Accept": "application/json;version=39.1",
                     "Authorization": f"Bearer {token}"}
            total_limit, total_used = 0, 0
            for urn in (cfg["storage_gold_urn"], cfg["storage_bronze_urn"]):
                base = cfg["base_url"]
                limit = requests.get(f"{base}/cloudapi/1.0.0/orgVdcStoragePolicies/{urn}",
                                     headers=heads, verify=False).json().get("storageLimitMb", 0)
                page, used_sum = 1, 0
                while True:
                    url = f"{base}/cloudapi/1.0.0/orgVdcStoragePolicies/{urn}/consumers?page={page}&pageSize=25"
                    resp = requests.get(url, headers=heads, verify=False)
                    if not resp.ok:
                        break
                    js = resp.json()
                    used_sum += sum(v.get("storageConsumedMb", 0) for v in js.get("values", []))
                    if page >= js.get("pageCount", 1):
                        break
                    page += 1
                total_limit += limit
                total_used += used_sum
            return total_limit / 1024 / 1024, total_used / 1024 / 1024  # в ТБ

        storage_tb, used_tb = get_storage_totals()
        logger.info(f"✅ Storage лимит {storage_tb:.2f} ТБ использовано {used_tb:.2f} ТБ")
        total_storage_gb = storage_tb * 1024 or 1  # делитель всегда >0

        # --- таблица vApp
        df = get_vapps(cfg, token, force_update=True)
        if df.empty:
            return "⚠️ Нет данных vApp."

        df["vCPU %"] = df["vCPU"] / cpu_vcpu * 100
        df["RAM %"] = df["RAM (ГБ)"] / ram_gb * 100
        df["Диск %"] = df["Диск (ГБ)"] / total_storage_gb * 100
        df = df.round({"RAM (ГБ)": 1, "Диск (ГБ)": 1,
                       "vCPU %": 2, "RAM %": 2, "Диск %": 2})

        total = {
            "Имя vApp": "ИТОГО",
            "vCPU": df["vCPU"].sum(),
            "RAM (ГБ)": df["RAM (ГБ)"].sum(),
            "Диск (ГБ)": df["Диск (ГБ)"].sum(),
            "vCPU %": df["vCPU"].sum() / cpu_vcpu * 100,
            "RAM %": df["RAM (ГБ)"].sum() / ram_gb * 100,
            "Диск %": df["Диск (ГБ)"].sum() / total_storage_gb * 100
        }

        widths = [max(20, max(len(x) for x in df["Имя vApp"]) + 2),
                  8, 9, 9, 8, 10, 10]
        headers = ["Имя vApp", "vCPU", "vCPU %", "RAM(ГБ)",
                   "RAM %", "Диск(ГБ)", "Диск %"]
        sep = "=" * (sum(widths) + len(widths) * 3 - 1)
        dash = "-" * (sum(widths) + len(widths) * 3 - 1)

        def fmt_row(values):
            parts = []
            for i, v in enumerate(values):
                t = str(v)
                parts.append(t.ljust(widths[i]) if i == 0 else t.center(widths[i]))
            return " | ".join(parts)

        lines = [sep, fmt_row(headers), dash]
        for _, r in df.iterrows():
            lines.append(fmt_row([
                r["Имя vApp"], int(r["vCPU"]),
                f"{r['vCPU %']:.1f}", f"{r['RAM (ГБ)']:.1f}",
                f"{r['RAM %']:.1f}", f"{r['Диск (ГБ)']:.1f}", f"{r['Диск %']:.1f}"]))
        lines += [sep, fmt_row([
            total["Имя vApp"], int(total["vCPU"]),
            f"{total['vCPU %']:.1f}", f"{total['RAM (ГБ)']:.1f}",
            f"{total['RAM %']:.1f}", f"{total['Диск (ГБ)']:.1f}",
            f"{total['Диск %']:.1f}"]), sep]

        text = "\n".join(lines)
        result = (
            f"<b>📊 Статистика всех vApp</b>\n"
            f"<pre>{text}</pre>"
        )
        logger.info(f"✅ Отчёт готов ({len(df)} vApp) за {time.time()-start:.2f}s")
        return result

    except Exception as e:
        logger.exception(f"❌ Ошибка формирования сводной статистики: {e}")
        return "❌ Ошибка при формировании статистики vApp."



def describe_single_vapp(cfg, token, vapp_name: str) -> str:
    """
    Формирует информацию о vApp.
    Если ВМ <= 10 — таблица; если больше — компактный мобильный формат.
    """
    try:
        # --- ищем ссылку на vApp ---
        df = get_vapps(cfg, token)
        row = df[df["Имя vApp"] == vapp_name]
        if row.empty:
            return f"⚠️ vApp <b>{vapp_name}</b> не найден."

        href = row.iloc[0]["href"]
        vapp_id = href.split("vapp-")[-1]
        url = f"{cfg['base_url']}/api/vApp/vapp-{vapp_id}"
        headers = {
            "Accept": "application/*+xml;version=40.0.0-alpha",
            "Authorization": f"Bearer {token}"
        }

        r = requests.get(url, headers=headers, verify=False, timeout=30)
        r.raise_for_status()
        xml_text = r.text
        ns = {"v": "http://www.vmware.com/vcloud/v1.5"}
        root = ET.fromstring(xml_text)
        vapp_name_xml = root.attrib.get("name", "?")
        vms = root.findall("v:Children/v:Vm", ns)
        if not vms:
            return f"⚠️ В vApp <b>{vapp_name_xml}</b> нет виртуальных машин."

        # --- сбор данных ---
        table_data = []
        total_cpu = total_ram = total_disk = total_snap_size = 0
        for vm in vms:
            name = vm.attrib.get("name", "-")
            storage = vm.find("v:StorageProfile", ns)
            storage_name = storage.attrib.get("name", "-") if storage is not None else "-"

            spec = vm.find("v:VmSpecSection", ns)
            cpu = ram_gb = disk_gb = 0
            if spec is not None:
                numcpu = spec.find("v:NumCpus", ns)
                if numcpu is not None and numcpu.text:
                    cpu = int(numcpu.text)
                mem = spec.find("v:MemoryResourceMb/v:Configured", ns)
                if mem is not None and mem.text:
                    ram_gb = round(int(mem.text) / 1024, 1)
                for d in spec.findall("v:DiskSection/v:DiskSettings/v:SizeMb", ns):
                    if d.text and d.text.isdigit():
                        disk_gb += int(d.text) / 1024

            nc = vm.find("v:NetworkConnectionSection/v:NetworkConnection", ns)
            net_name = nc.attrib.get("network", "-") if nc is not None else "-"
            ip_el = nc.find("v:IpAddress", ns) if nc is not None else None
            ip_addr = ip_el.text if ip_el is not None else "-"

            snap_section = vm.find("v:SnapshotSection", ns)
            snap_count = 0
            snap_size_gb = 0.0
            if snap_section is not None:
                for s in snap_section.findall("v:Snapshot", ns):
                    snap_count += 1
                    try:
                        snap_size_gb += int(s.attrib.get("size", "0")) / 1024**3
                    except ValueError:
                        pass

            total_cpu += cpu
            total_ram += ram_gb
            total_disk += disk_gb
            total_snap_size += snap_size_gb

            table_data.append([name, net_name, ip_addr, cpu, ram_gb,
                               round(disk_gb, 1), storage_name, snap_count, round(snap_size_gb, 1)])

        # --- выбор формата ---
        if len(table_data) <= 10:
            # таблица для ПК
            header = ["Имя ВМ", "Network", "IP", "CPU", "RAM", "Disk", "Storage", "Snaps", "SnapSize"]
            col_widths = [22, 18, 14, 4, 6, 7, 8, 5, 10]

            def fmt_row(cols):
                parts = []
                for i, w in enumerate(col_widths):
                    val = str(cols[i])
                    parts.append(val.ljust(w) if i < 3 else val.center(w))
                return " | ".join(parts)

            sep_line = "-" * (sum(col_widths) + len(col_widths)*3 - 1)
            lines = [fmt_row(header), sep_line]
            for row in table_data:
                lines.append(fmt_row(row))
            lines.append(sep_line)
            lines.append(
                fmt_row([
                    "ИТОГО", f"VMs:{len(table_data)}", "",
                    total_cpu, f"{total_ram:.1f}", f"{total_disk:.1f}",
                    "", "", f"{total_snap_size:.1f}",
                ])
            )
            table = "\n".join(lines)
            return f"<b>📦 vApp: {vapp_name_xml}</b>\n<pre>{table}</pre>"

        else:
            # компактный мобильный формат
            lines = [f"<b>📦 vApp: {vapp_name_xml}</b>", "───────────────────────"]
            for name, net, ip, cpu, ram, disk, storage, snaps, snap_size in table_data:
                lines.append(
                    f"<b>{name}</b>\n"
                    f"• CPU: {cpu}, RAM: {ram} GB, Disk: {disk} GB\n"
                    f"• Net: {net} ({ip})\n"
                    f"• Storage: {storage}, Snaps: {snaps} ({snap_size} GB)\n"
                    "—————"
                )
            lines.append(
                f"<b>ИТОГО:</b> {len(table_data)} VM⠀│ CPU {total_cpu} │ RAM {total_ram:.1f} GB │ Disk {total_disk:.1f} GB │ Snaps {total_snap_size:.1f} GB"
            )
            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Ошибка информации vApp {vapp_name}: {e}")
        return f"❌ Ошибка при получении информации о <b>{vapp_name}</b>."


def describe_single_vapp_pc(cfg, token, vapp_name: str) -> str:
    """
    Возвращает красивую широкую таблицу ВМ внутри vApp (ПК‑вид).
    Добавлено подробное логирование.
    """
    start_ts = time.time()
    logger.info(f"📥 Запрос детальной таблицы vApp '{vapp_name}'")

    try:
        df = get_vapps(cfg, token)
        row = df[df["Имя vApp"] == vapp_name]
        if row.empty:
            logger.warning(f"⚠️ vApp '{vapp_name}' не найден в списке vApp.")
            return f"⚠️ vApp <b>{vapp_name}</b> не найден."

        href = row.iloc[0]["href"]
        vapp_id = href.split("vapp-")[-1]
        url = f"{cfg['base_url']}/api/vApp/vapp-{vapp_id}"
        headers = {"Accept": "application/*+xml;version=40.0.0-alpha",
                   "Authorization": f"Bearer {token}"}

        r = requests.get(url, headers=headers, verify=False, timeout=30)
        r.raise_for_status()
        xml_text = r.text

        ns = {"v": "http://www.vmware.com/vcloud/v1.5"}
        root = ET.fromstring(xml_text)
        vapp_name_xml = root.attrib.get("name", "?")
        vms = root.findall("v:Children/v:Vm", ns)

        if not vms:
            logger.info(f"⚠️ vApp '{vapp_name}' пуст (нет ВМ)")
            return f"⚠️ В vApp <b>{vapp_name_xml}</b> нет виртуальных машин."

        table_data = []
        total_cpu = total_ram = total_disk = total_snap = 0

        for vm in vms:
            name = vm.attrib.get("name", "-")
            storage = vm.find("v:StorageProfile", ns)
            storage_name = storage.attrib.get("name", "-") if storage is not None else "-"
            spec = vm.find("v:VmSpecSection", ns)
            cpu = ram_gb = disk_gb = 0
            if spec is not None:
                numcpu = spec.find("v:NumCpus", ns)
                if numcpu is not None and numcpu.text:
                    cpu = int(numcpu.text)
                mem = spec.find("v:MemoryResourceMb/v:Configured", ns)
                if mem is not None and mem.text:
                    ram_gb = round(int(mem.text)/1024, 1)
                for d in spec.findall("v:DiskSection/v:DiskSettings/v:SizeMb", ns):
                    if d.text and d.text.isdigit():
                        disk_gb += int(d.text)/1024

            nc = vm.find("v:NetworkConnectionSection/v:NetworkConnection", ns)
            net = nc.attrib.get("network", "-") if nc is not None else "-"
            ip_el = nc.find("v:IpAddress", ns) if nc is not None else None
            ip = ip_el.text if ip_el is not None else "-"

            snap_section = vm.find("v:SnapshotSection", ns)
            sn_count = 0
            sn_size = 0.0
            if snap_section is not None:
                for s in snap_section.findall("v:Snapshot", ns):
                    sn_count += 1
                    try:
                        sn_size += int(s.attrib.get("size", "0"))/1024**3
                    except ValueError:
                        pass

            total_cpu += cpu
            total_ram += ram_gb
            total_disk += disk_gb
            total_snap += sn_size

            table_data.append([
                name, net, ip, cpu, f"{ram_gb:.1f}", f"{disk_gb:.1f}",
                storage_name, sn_count, f"{sn_size:.1f}"
            ])

        # --- оформление таблицы ---
        header = ["Имя ВМ", "Network", "IP‑Address", "CPU", "RAM(GB)",
                  "Disk(GB)", "Storage", "Snaps", "Snap Size(GB)"]
        col_widths = [25, 25, 17, 4, 8, 9, 10, 5, 13]
        sep_line = "=" * (sum(col_widths) + len(col_widths)*3 - 1)
        dash_line = "-" * (sum(col_widths) + len(col_widths)*3 - 1)

        def fmt_row(cols, widths):
            parts = []
            for i, w in enumerate(widths):
                val = str(cols[i])
                parts.append(val.ljust(w) if i < 3 else val.center(w))
            return " | ".join(parts)

        lines = [sep_line, fmt_row(header, col_widths), dash_line]
        for row in table_data:
            lines.append(fmt_row(row, col_widths))
        lines.append(sep_line)
        lines.append(fmt_row([
            "ИТОГО", f"VM count: {len(table_data)}", "",
            total_cpu, f"{total_ram:.1f}", f"{total_disk:.1f}", "",
            "", f"{total_snap:.1f}"
        ], col_widths))
        lines.append(sep_line)

        elapsed = time.time() - start_ts
        logger.info(
            f"✅ Отчёт по vApp '{vapp_name}' готов: {len(table_data)} ВМ, "
            f"{elapsed:.1f}s, CPU {total_cpu}, RAM {total_ram:.1f} GB, Disk {total_disk:.1f} GB."
        )

        table_text = "\n".join(lines)
        return f"<b>📦 vApp: {vapp_name_xml}</b>\n<pre>{table_text}</pre>"

    except Exception as e:
        logger.exception(f"Ошибка информации vApp {vapp_name}: {e}")
        return f"❌ Ошибка при получении информации о <b>{vapp_name}</b>."


# ------------------------------------------------------------------------------
# HANDLERS
# ------------------------------------------------------------------------------
@router.message(Command("cloudvapp"))
async def cloudvapp_start(message: types.Message):
    """Команда /cloudvapp — запрос и показ списка vApp"""
    try:
        await message.answer("🔄 Получаю список vApp…")
        token = get_bearer_token(CONFIG)
        df = get_vapps(CONFIG, token)
        if df.empty:
            await message.answer("⚠️ vApp не найдены.")
            return
        await message.answer("📦 Выбери vApp из списка:", reply_markup=keyboard_vapp_list(df))
    except Exception as e:
        logger.error(f"Ошибка /cloudvapp: {e}")
        await message.answer("❌ Ошибка при запросе списка vApp.")


@router.callback_query(lambda c: c.data == "allvapp_csv")
async def callback_allvapp_csv(callback: types.CallbackQuery):
    """Экспорт CSV по всем vApp (полная информация + проценты)."""
    import io
    logger.info("📤 Запрошен экспорт CSV для всех vApp")
    try:
        token = get_bearer_token(CONFIG)
        df = get_vapps(CONFIG, token, force_update=True)
        if df.empty:
            await callback.answer("⚠️ Нет данных о vApp.", show_alert=True)
            return

        # --- заменяем эмодзи статусов на текст
        emoji_to_text = {"🟢": "POWERED_ON", "🔴": "POWERED_OFF",
                         "🟡": "MIXED", "⚪": "UNKNOWN"}
        df["Статус (текст)"] = df["Статус"].replace(emoji_to_text)  # Обычный пробел

        # --- получаем лимиты CPU/RAM/Storage, как в summarize_all_vapps
        url_vdc = f"{CONFIG['base_url']}/api/vdc/{CONFIG['vdc_id']}"
        hdrs = {"Accept": "application/*+xml;version=39.1",
                "Authorization": f"Bearer {token}"}
        r = requests.get(url_vdc, headers=hdrs, verify=False)
        ns = {"v": "http://www.vmware.com/vcloud/v1.5"}
        root = ET.fromstring(r.text)
        cpu_vcpu = int(root.find(".//v:Cpu/v:Allocated", ns).text) / 1000 / 1.73
        ram_gb = int(root.find(".//v:Memory/v:Allocated", ns).text) / 1024

        storage_tb = get_storage_limits(CONFIG, token)
        total_storage_gb = storage_tb * 1024 or 1

        # --- расчёт процентов
        df["vCPU %"] = df["vCPU"] / cpu_vcpu * 100
        df["RAM %"] = df["RAM (ГБ)"] / ram_gb * 100
        df["Диск %"] = df["Диск (ГБ)"] / total_storage_gb * 100
        df = df.round({
            "RAM (ГБ)": 1, "Диск (ГБ)": 1,
            "vCPU %": 2, "RAM %": 2, "Диск %": 2,
        })

        # --- строка ИТОГО
        total_row = {
            "Статус (текст)": "",
            "Имя vApp": "ИТОГО",  # Обычный пробел
            "vCPU": df["vCPU"].sum(),
            "vCPU %": df["vCPU"].sum() / cpu_vcpu * 100,
            "RAM (ГБ)": df["RAM (ГБ)"].sum(),
            "RAM %": df["RAM (ГБ)"].sum() / ram_gb * 100,
            "Диск (ГБ)": df["Диск (ГБ)"].sum(),
            "Диск %": df["Диск (ГБ)"].sum() / total_storage_gb * 100,
        }
        df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

        # --- выбираем колонки и экспортируем
        cols = ["Статус (текст)", "Имя vApp", "vCPU", "vCPU %",  # Все с обычными пробелами
                "RAM (ГБ)", "RAM %", "Диск (ГБ)", "Диск %"]
        df = df[cols]

        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)

        await callback.message.answer_document(
            types.BufferedInputFile(
                buf.read().encode("utf-8"),
                filename="vApps_All_Info.csv"
            ),
            caption="📄 Экспорт всех vApp (полный отчёт)",
            parse_mode="HTML"
        )
        logger.info(f"✅ CSV экспорт успешен: {len(df)-1} vApp + итого")
        await callback.answer()

    except Exception as e:
        logger.exception(f"❌ Ошибка экспорта всех vApp в CSV: {e}")
        await callback.answer("Ошибка CSV‑экспорта.", show_alert=True)



@router.callback_query(lambda c: c.data.startswith("page:"))
async def callback_page(callback: types.CallbackQuery):
    """Перелистывание"""
    try:
        page = int(callback.data.split(":")[1])
        token = get_bearer_token(CONFIG)
        df = get_vapps(CONFIG, token)
        kb = keyboard_vapp_list(df, page)
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка пагинации: {e}")
        await callback.answer("Ошибка пагинации.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("vapp:") and c.data != "vapp:stats")
async def callback_vapp(callback: types.CallbackQuery):
    """Выбор конкретного vApp"""
    name = callback.data.split(":", 1)[1]
    text = f"📦 vApp: <b>{name}</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard_vapp_detail(name))
    await callback.answer()


@router.callback_query(lambda c: c.data == "vapp:stats")
async def callback_stats(callback: types.CallbackQuery):
    """
    Показывает общую статистику всех vApp —
    таблица + только кнопка "Назад".
    """
    try:
        token = get_bearer_token(CONFIG)
        text = summarize_all_vapps(CONFIG, token)

        # одна единственная кнопка "Назад"
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back:vapp_list"))

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка отображения статистики: {e}")
        await callback.answer("Ошибка отображения статистики.", show_alert=True)


@router.callback_query(lambda c: c.data == "allvapp_mobile")
async def callback_allvapp_mobile(callback: types.CallbackQuery):
    """
    📱 Мобильный формат общей статистики по всем vApp —
    краткие карточки как при отображении одной vApp,
    с добавлением процентов в итогах.
    """
    try:
        token = get_bearer_token(CONFIG)
        df = get_vapps(CONFIG, token, force_update=True)
        if df.empty:
            await callback.answer("⚠️ Нет данных о vApp.", show_alert=True)
            return

        # --- лимиты для процентов ---
        vdc_url = f"{CONFIG['base_url']}/api/vdc/{CONFIG['vdc_id']}"
        hdrs = {
            "Accept": "application/*+xml;version=39.1",
            "Authorization": f"Bearer {token}"
        }
        r = requests.get(vdc_url, headers=hdrs, verify=False)
        r.raise_for_status()
        ns = {"v": "http://www.vmware.com/vcloud/v1.5"}
        root = ET.fromstring(r.text)
        cpu_vcpu = int(root.find(".//v:Cpu/v:Allocated", ns).text) / 1000 / 1.73
        ram_gb = int(root.find(".//v:Memory/v:Allocated", ns).text) / 1024

        storage_tb = get_storage_limits(CONFIG, token)
        total_storage_gb = storage_tb * 1024 or 1

        df["vCPU %"] = df["vCPU"] / cpu_vcpu * 100
        df["RAM %"] = df["RAM (ГБ)"] / ram_gb * 100
        df["Диск %"] = df["Диск (ГБ)"] / total_storage_gb * 100
        df = df.round({"RAM (ГБ)": 1, "Диск (ГБ)": 1,
                       "vCPU %": 1, "RAM %": 1, "Диск %": 1})

        # --- формирование карточек ---
        lines = ["<b>📊 Статистика всех vApp</b>", "───────────────────────"]
        total_cpu = df["vCPU"].sum()
        total_ram = df["RAM (ГБ)"].sum()
        total_disk = df["Диск (ГБ)"].sum()

        total_cpu_pct = total_cpu / cpu_vcpu * 100
        total_ram_pct = total_ram / ram_gb * 100
        total_disk_pct = total_disk / total_storage_gb * 100

        for _, r in df.iterrows():
            name = r["Имя vApp"]
            lines.append(
                f"<b>{name}</b>\n"
                f"• CPU {r['vCPU']} ({r['vCPU %']:.1f} %)\n"
                f"• RAM {r['RAM (ГБ)']:.1f} GB ({r['RAM %']:.1f} %)\n"
                f"• Disk {r['Диск (ГБ)']:.1f} GB ({r['Диск %']:.1f} %)\n"
                "—————"
            )

        # --- итог ---
        lines.append(
            f"<b>ИТОГО:</b> {len(df)} vApp │ "
            f"CPU {int(total_cpu)} ({total_cpu_pct:.1f} %) │ "
            f"RAM {total_ram:.1f} GB ({total_ram_pct:.1f} %) │ "
            f"Disk {total_disk:.1f} GB ({total_disk_pct:.1f} %)"
        )

        text = "\n".join(lines)

        # --- клавиатура «Назад» ---
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back:vapp_list"))

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка Mobile‑статистики всех vApp: {e}")
        await callback.answer("Ошибка отображения Mobile‑версии.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("vappinfo:"))
async def callback_info(callback: types.CallbackQuery):
    """Информация по выбранному vApp"""
    vapp_name = callback.data.split(":", 1)[1]
    try:
        token = get_bearer_token(CONFIG)
        text = describe_single_vapp(CONFIG, token, vapp_name)
        await callback.message.edit_text(
            text, parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back:vapp_list")]]
            )
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка информации vApp: {e}")
        await callback.answer("Ошибка отображения информации.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("back:"))
async def callback_back(callback: types.CallbackQuery):
    """Обработка кнопок 'Назад'"""
    try:
        action = callback.data.split(":", 1)[1]

        if action == "vapp_list":
            # Возвращаем список vApp
            token = get_bearer_token(CONFIG)
            df = get_vapps(CONFIG, token)
            kb = keyboard_vapp_list(df, page=1)
            await callback.message.edit_text(
                "📦 Выбери vApp из списка:",
                reply_markup=kb
            )
            await callback.answer()
            return

        # Все остальные «Назад», включая main, просто игнорируем
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка кнопки 'Назад': {e}")
        await callback.answer("Ошибка возврата.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("vappinfo_pc:"))
async def callback_vapp_info_pc(callback: types.CallbackQuery):
    """Информация vApp в широком табличном (ПК) виде"""
    vapp_name = callback.data.split(":", 1)[1]
    try:
        token = get_bearer_token(CONFIG)
        text = describe_single_vapp_pc(CONFIG, token, vapp_name)
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard_vapp_detail(vapp_name)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка PC‑инфо vApp: {e}")
        await callback.answer("Ошибка получения данных для ПК.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("vappinfo_mobile:"))
async def callback_vapp_info_mobile(callback: types.CallbackQuery):
    """Информация vApp в мобильном (карточном) виде"""
    vapp_name = callback.data.split(":", 1)[1]
    try:
        token = get_bearer_token(CONFIG)
        # принудительно показать компактный вид
        original_describe = describe_single_vapp(CONFIG, token, vapp_name)
        # вырежем кодовый блок и сделаем короткие строки
        mobile_text = (
            original_describe
            .replace("<pre>", "")
            .replace("</pre>", "")
            .replace("|", "│")
            .replace("=", "─")
            .replace("-", "·")
        )
        await callback.message.edit_text(
            mobile_text,
            parse_mode="HTML",
            reply_markup=keyboard_vapp_detail(vapp_name)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка Mobile‑инфо vApp: {e}")
        await callback.answer("Ошибка получения Mobile‑версии.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("vappinfo_csv:"))
async def callback_vapp_info_csv(callback: types.CallbackQuery):
    """Формирует и отправляет CSV‑файл с полными данными (как в PC‑таблице)"""
    import io
    vapp_name = callback.data.split(":", 1)[1]
    logger.info(f"📤 Запрос экспорта CSV для vApp '{vapp_name}'")
    try:
        token = get_bearer_token(CONFIG)
        ns = {"v": "http://www.vmware.com/vcloud/v1.5"}

        # получим XML нужного vApp
        df = get_vapps(CONFIG, token)
        row = df[df["Имя vApp"] == vapp_name]
        if row.empty:
            await callback.answer("vApp не найден.", show_alert=True)
            return
        href = row.iloc[0]["href"]
        vapp_id = href.split("vapp-")[-1]
        url = f"{CONFIG['base_url']}/api/vApp/vapp-{vapp_id}"
        headers = {
            "Accept": "application/*+xml;version=40.0.0-alpha",
            "Authorization": f"Bearer {token}"
        }
        r = requests.get(url, headers=headers, verify=False, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        vms = root.findall("v:Children/v:Vm", ns)

        data = []
        total_cpu = total_ram = total_disk = total_snap = 0
        for vm in vms:
            name = vm.attrib.get("name", "-")
            spec = vm.find("v:VmSpecSection", ns)
            cpu = 0
            ram_gb = disk_gb = 0.0
            if spec is not None:
                numcpu = spec.find("v:NumCpus", ns)
                if numcpu is not None and numcpu.text:
                    cpu = int(numcpu.text)
                mem = spec.find("v:MemoryResourceMb/v:Configured", ns)
                if mem is not None and mem.text.isdigit():
                    ram_gb = round(int(mem.text) / 1024, 1)
                for d in spec.findall("v:DiskSection/v:DiskSettings/v:SizeMb", ns):
                    if d.text and d.text.isdigit():
                        disk_gb += int(d.text) / 1024

            nc = vm.find("v:NetworkConnectionSection/v:NetworkConnection", ns)
            net = nc.attrib.get("network", "-") if nc is not None else "-"
            ip = ""
            ip_el = nc.find("v:IpAddress", ns) if nc is not None else None
            if ip_el is not None and ip_el.text:
                ip = ip_el.text

            storage = vm.find("v:StorageProfile", ns)
            storage_name = storage.attrib.get("name", "-") if storage is not None else "-"

            snap_count = 0
            snap_size_gb = 0.0
            snap_section = vm.find("v:SnapshotSection", ns)
            if snap_section is not None:
                for s in snap_section.findall("v:Snapshot", ns):
                    snap_count += 1
                    try:
                        snap_size_gb += int(s.attrib.get("size", "0")) / 1024**3
                    except ValueError:
                        pass

            total_cpu += cpu
            total_ram += ram_gb
            total_disk += disk_gb
            total_snap += snap_size_gb

            data.append({
                "Имя ВМ": name,
                "Network": net,
                "IP‑Address": ip,
                "CPU": cpu,
                "RAM(GB)": ram_gb,
                "Disk(GB)": round(disk_gb, 1),
                "Storage": storage_name,
                "Snaps": snap_count,
                "Snap Size(GB)": round(snap_size_gb, 1)
            })

        # добавим итоговую строку
        data.append({
            "Имя ВМ": "ИТОГО",
            "Network": f"VM count: {len(vms)}",
            "IP‑Address": "",
            "CPU": total_cpu,
            "RAM(GB)": round(total_ram, 1),
            "Disk(GB)": round(total_disk, 1),
            "Storage": "",
            "Snaps": "",
            "Snap Size(GB)": round(total_snap, 1),
        })
        logger.info(f"🧮 Собрано {len(vms)} ВМ для CSV '{vapp_name}'")

        # генерим CSV
        df_out = pd.DataFrame(data)
        buf = io.StringIO()
        df_out.to_csv(buf, index=False)
        buf.seek(0)
        await callback.message.answer_document(
            types.BufferedInputFile(buf.read().encode("utf-8"), filename=f"{vapp_name}.csv"),
            caption=f"📄 Экспорт vApp <b>{vapp_name}</b>",
            parse_mode="HTML"
        )
        logger.info(f"✅ Файл CSV ('{vapp_name}.csv') отправлен, {len(df_out)} строк.")
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка CSV‑экспорта vApp {vapp_name}: {e}")
        await callback.answer("Ошибка при формировании CSV.", show_alert=True)