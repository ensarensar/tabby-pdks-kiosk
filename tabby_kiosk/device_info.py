# -*- coding: utf-8 -*-
"""
Tabby kiosk cihaz kimlik bilgileri.
Ekranda gosterilen IP/MAC: aktif arayuzden okunan canli degerler.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any, Dict

from config_store import oku_config

_PROJE_KOKU = os.path.dirname(os.path.abspath(__file__))
_CONFIG_DIZINI = os.environ.get(
    "TABBY_CONFIG_DIR",
    os.path.join(os.path.expanduser("~"), ".config", "tabby-kiosk"),
)
_CIHAZ_DOSYASI = os.environ.get(
    "TABBY_DEVICE_INFO_FILE", os.path.join(_CONFIG_DIZINI, "device_info.json")
)
_ESKI_CIHAZ_DOSYASI = os.path.join(_PROJE_KOKU, "device_info.json")


@dataclass
class CihazBilgisi:
    cihaz_adi: str
    cihaz_ip: str
    cihaz_mac: str

    def payload_dict(self) -> Dict[str, str]:
        return {
            "cihaz_adi": self.cihaz_adi,
            "cihaz_ip": self.cihaz_ip,
            "cihaz_mac": self.cihaz_mac,
        }


def _varsayilan_mac() -> str:
    mac = uuid.getnode()
    return ":".join(f"{(mac >> eleman) & 0xFF:02x}" for eleman in range(40, -1, -8))


def _varsayilan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.85.1.130", 80))
            ip = s.getsockname()[0]
            if ip:
                return ip
    except OSError:
        pass
    try:
        adaylar = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        for kayit in adaylar:
            ip = kayit[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "-"


def _arayuz_aktif_ip(arayuz: str) -> str:
    if not arayuz:
        return ""
    try:
        p = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "dev", arayuz],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return ""
    if p.returncode != 0:
        return ""
    for satir in (p.stdout or "").splitlines():
        parcali = satir.split()
        if "inet" not in parcali:
            continue
        try:
            i = parcali.index("inet")
            cidr = parcali[i + 1]
            ip = cidr.split("/")[0].strip()
            if ip:
                return ip
        except Exception:
            continue
    return ""


def _arayuz_mac(arayuz: str) -> str:
    if not arayuz:
        return ""
    yol = "/sys/class/net/%s/address" % arayuz
    if not os.path.isfile(yol):
        return ""
    try:
        with open(yol, "r", encoding="utf-8") as f:
            mac = f.read().strip()
    except Exception:
        return ""
    return mac.upper() if mac else ""


def _varsayilan() -> CihazBilgisi:
    return CihazBilgisi(
        cihaz_adi=(socket.gethostname() or "-").strip(),
        cihaz_ip=_varsayilan_ip(),
        cihaz_mac=_varsayilan_mac(),
    )


def oku_cihaz_bilgisi() -> CihazBilgisi:
    d = _varsayilan()
    cfg = oku_config()
    if not isinstance(cfg, dict):
        cfg = {}

    eth_if = str(cfg.get("ethernet_interface", "eth0")).strip() or "eth0"
    wifi_if = str(cfg.get("wifi_interface", "wlan0")).strip() or "wlan0"
    cihaz_adi = str(cfg.get("cihaz_adi", "")).strip()
    eth_hedef_ip = str(cfg.get("cihaz_ip", "")).strip()

    eth_ip = _arayuz_aktif_ip(eth_if)
    wifi_ip = _arayuz_aktif_ip(wifi_if)
    eth_mac = _arayuz_mac(eth_if)
    wifi_mac = _arayuz_mac(wifi_if)

    if eth_ip:
        return CihazBilgisi(
            cihaz_adi=cihaz_adi or d.cihaz_adi,
            cihaz_ip=eth_ip or eth_hedef_ip or d.cihaz_ip,
            cihaz_mac=eth_mac or d.cihaz_mac,
        )
    if wifi_ip:
        return CihazBilgisi(
            cihaz_adi=cihaz_adi or d.cihaz_adi,
            cihaz_ip=wifi_ip or eth_hedef_ip or d.cihaz_ip,
            cihaz_mac=wifi_mac or eth_mac or d.cihaz_mac,
        )

    kaynak = _CIHAZ_DOSYASI
    if not os.path.isfile(kaynak) and os.path.isfile(_ESKI_CIHAZ_DOSYASI):
        kaynak = _ESKI_CIHAZ_DOSYASI
    if os.path.isfile(kaynak):
        try:
            with open(kaynak, "r", encoding="utf-8") as f:
                ham: Dict[str, Any] = json.load(f)
            return CihazBilgisi(
                cihaz_adi=str(ham.get("cihaz_adi", cihaz_adi or d.cihaz_adi)).strip()
                or (cihaz_adi or d.cihaz_adi),
                cihaz_ip=str(ham.get("cihaz_ip", eth_hedef_ip or d.cihaz_ip)).strip()
                or (eth_hedef_ip or d.cihaz_ip),
                cihaz_mac=eth_mac or wifi_mac or d.cihaz_mac,
            )
        except Exception:
            pass

    return CihazBilgisi(
        cihaz_adi=cihaz_adi or d.cihaz_adi,
        cihaz_ip=eth_hedef_ip or d.cihaz_ip,
        cihaz_mac=eth_mac or wifi_mac or d.cihaz_mac,
    )


_BAGLANTI_METIN = {
    "ethernet": "Ethernet",
    "wifi": "WiFi",
    "none": "Baglanti yok",
    "unknown": "Bilinmiyor",
}


def oku_ekran_bilgisi() -> Dict[str, str]:
    """Aktif ag arayuzu: tip, canli IP ve MAC + failover status dosyasi."""
    from heartbeat import heartbeat_payload_uret

    cfg = oku_config()
    if not isinstance(cfg, dict):
        cfg = {}
    cihaz_adi = str(cfg.get("cihaz_adi", "") or socket.gethostname() or "-").strip()
    wifi_if = str(cfg.get("wifi_interface", "wlan0")).strip() or "wlan0"

    ozet = heartbeat_payload_uret()
    tip = str(ozet.get("connection_type") or "unknown").strip().lower()
    metin = _BAGLANTI_METIN.get(tip, "Bilinmiyor")

    failover_tip = ""
    failover_detay = ""
    try:
        with open("/var/lib/tabby-kiosk/failover.status", "r", encoding="utf-8") as f:
            satirlar = [ln.strip() for ln in f.readlines()]
        if satirlar:
            failover_tip = satirlar[0]
        if len(satirlar) > 1:
            failover_detay = satirlar[1]
    except Exception:
        pass

    if tip == "ethernet":
        ip = str(ozet.get("ethernet_ip") or ozet.get("ip") or "").strip()
        mac = str(ozet.get("ethernet_mac") or ozet.get("mac") or "").strip()
        metin = "Ethernet"
    elif tip == "wifi":
        ip = str(ozet.get("wifi_ip") or ozet.get("ip") or "").strip()
        mac = str(ozet.get("wifi_mac") or ozet.get("mac") or "").strip()
        ssid = str(ozet.get("ssid") or "").strip()
        metin = "WiFi (%s)" % ssid if ssid else "WiFi"
    else:
        ip = "-"
        mac = str(ozet.get("wifi_mac") or "").strip() or _arayuz_mac(wifi_if) or "-"
        # tip ethernet/wifi degil: canli ag yok. Eski failover "eth_ok"
        # kablo sokulunce yaniltici "Ethernet" gostermesin.
        if failover_tip == "wifi_trying":
            # Bu "Access Controller'a HTTP/Radius gitti" demek DEGIL;
            # yerelde nmcli connection up cagrildi demektir.
            metin = "nmcli WiFi UP cagrildi..."
        elif failover_tip == "wifi_fail":
            metin = "WiFi UP basarisiz (log)"
        elif failover_tip == "wifi_ok":
            metin = "WiFi"
        else:
            metin = "Baglanti yok"

    if not ip:
        ip = "-"

    return {
        "cihaz_adi": cihaz_adi,
        "baglanti_tipi": tip,
        "baglanti_metin": metin,
        "ip": ip,
        "mac": mac.upper() if mac and mac != "-" else "-",
        "failover": failover_tip,
        "failover_detay": failover_detay,
    }
