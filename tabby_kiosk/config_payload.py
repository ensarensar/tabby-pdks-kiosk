# -*- coding: utf-8 -*-
"""
Sunucudan gelen config JSON'unu cihaz alan adlarina cevirir, dogrular ve kaydeder.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

from config_store import oku_config, yaz_config

# Cihazda kalici tutulacak alanlar
IZINLI_ALANLAR = frozenset(
    {
        "cihaz_adi",
        "cihaz_ip",
        "subnet_mask",
        "subnet_musk",
        "gateway",
        "dns",
        "ntp_server",
        "wifi_ssid",
        "wifi_password",
        "wifi_hidden",
        "wifi_interface",
        "ethernet_interface",
        "servis_url",
        "servis_timeout_s",
        "kart_okuma_endpoint",
        "bekleme_video_kullanici",
        "bekleme_video_sifre",
        "bekleme_video_login_url",
        "bekleme_video_baslama_saniye",
        "heartbeat_url",
        "heartbeat_interval_s",
        "heartbeat_timeout_s",
        "heartbeat_aktif",
        "reboot_after_apply",
    }
)

# Sunucu (camelCase / farkli ad) -> cihaz (snake_case)
ALAN_ESLESTIRME: Dict[str, str] = {
    "heartbeatAktif": "heartbeat_aktif",
    "heartbeatIntervalS": "heartbeat_interval_s",
    "heartbeatTimeoutS": "heartbeat_timeout_s",
    "heartbeatUrl": "heartbeat_url",
    "subnetMask": "subnet_mask",
    "wifiSsid": "wifi_ssid",
    "wifiPassword": "wifi_password",
    "wifiHidden": "wifi_hidden",
    "wifiInterface": "wifi_interface",
    "ethernetInterface": "ethernet_interface",
    "servisUrl": "servis_url",
    "servisTimeoutS": "servis_timeout_s",
    "kartOkumaEndpoint": "kart_okuma_endpoint",
    "cihazAdi": "cihaz_adi",
    "cihazIp": "cihaz_ip",
    "ntpServer": "ntp_server",
    "rebootAfterApply": "reboot_after_apply",
    "beklemeVideoKullanici": "bekleme_video_kullanici",
    "beklemeVideoSifre": "bekleme_video_sifre",
    "beklemeVideoLoginUrl": "bekleme_video_login_url",
    "beklemeVideoBaslamaSaniye": "bekleme_video_baslama_saniye",
}


def _sunucu_alanini_yoksay(anahtar: str) -> bool:
    if anahtar.startswith("sonHeartbeat") or anahtar.startswith("sonPing"):
        return True
    if anahtar in (
        "id",
        "createdAt",
        "updatedAt",
        "deletedAt",
        "version",
    ):
        return True
    return False


def normalize_sunucu_payload(veri: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    """Sunucu JSON'unu cihaz alan adlarina cevir; yoksayilan alanlari raporla."""
    if not isinstance(veri, dict):
        return ({}, [])
    yoksayilan: list[str] = []
    birlesik: Dict[str, Any] = {}
    for anahtar, deger in veri.items():
        if _sunucu_alanini_yoksay(anahtar):
            yoksayilan.append(anahtar)
            continue
        hedef = ALAN_ESLESTIRME.get(anahtar, anahtar)
        if hedef not in IZINLI_ALANLAR:
            yoksayilan.append(anahtar)
            continue
        birlesik[hedef] = deger
    return (birlesik, yoksayilan)


def _ipv4_gecerli(v: str) -> bool:
    try:
        ipaddress.IPv4Address(v)
        return True
    except Exception:
        return False


def _mask_gecerli(mask: str) -> bool:
    p = (mask or "").split(".")
    if len(p) != 4:
        return False
    try:
        b = "".join(f"{int(x):08b}" for x in p)
    except Exception:
        return False
    return "01" not in b


def _bool_alan(deger: Any, alan: str) -> Tuple[bool, Any | str]:
    if isinstance(deger, bool):
        return (True, deger)
    if isinstance(deger, (int, float)) and deger in (0, 1):
        return (True, bool(deger))
    if isinstance(deger, str):
        rbv = deger.strip().lower()
        if rbv in ("1", "true", "yes", "on"):
            return (True, True)
        if rbv in ("0", "false", "no", "off", ""):
            return (True, False)
    return (False, "%s true/false olmali" % alan)


def validate_config_payload(veri: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    ham, _yoksay = normalize_sunucu_payload(veri)
    temiz: Dict[str, Any] = {}
    for anahtar in IZINLI_ALANLAR:
        if anahtar not in ham:
            continue
        deger = ham.get(anahtar)
        if isinstance(deger, str):
            temiz[anahtar] = deger.strip()
        else:
            temiz[anahtar] = deger
    if not temiz:
        return (
            False,
            "ayarlanacak alan yok (cihaz alan adlari snake_case olmali; "
            "sunucu durum alanlari sonHeartbeat*/sonPing* gonderilmemeli)",
            {},
        )

    if temiz.get("kart_okuma_endpoint") and not temiz.get("servis_url"):
        temiz["servis_url"] = str(temiz.get("kart_okuma_endpoint", "")).strip()
    if temiz.get("subnet_musk") and not temiz.get("subnet_mask"):
        temiz["subnet_mask"] = str(temiz.get("subnet_musk", "")).strip()

    for url_alan in ("servis_url", "bekleme_video_login_url", "heartbeat_url"):
        if not temiz.get(url_alan):
            continue
        su = str(temiz.get(url_alan, "")).strip()
        parsed = urlparse(su)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return (False, "%s gecersiz" % url_alan, {})
        temiz[url_alan] = su

    if temiz.get("servis_timeout_s") not in (None, ""):
        try:
            t = float(temiz.get("servis_timeout_s"))
        except (TypeError, ValueError):
            return (False, "servis_timeout_s sayi olmali", {})
        temiz["servis_timeout_s"] = max(1.0, min(t, 30.0))

    if temiz.get("bekleme_video_baslama_saniye") not in (None, ""):
        try:
            t = float(temiz.get("bekleme_video_baslama_saniye"))
        except (TypeError, ValueError):
            return (False, "bekleme_video_baslama_saniye sayi olmali", {})
        temiz["bekleme_video_baslama_saniye"] = max(1.0, min(t, 86400.0))

    for alan in ("heartbeat_interval_s", "heartbeat_timeout_s"):
        if temiz.get(alan) in (None, ""):
            continue
        try:
            t = float(temiz.get(alan))
        except (TypeError, ValueError):
            return (False, "%s sayi olmali" % alan, {})
        if t <= 0:
            return (False, "%s pozitif sayi olmali" % alan, {})
        temiz[alan] = max(1.0, min(t, 86400.0))

    for alan in ("cihaz_ip", "gateway", "ntp_server"):
        v = str(temiz.get(alan, "")).strip()
        if not v:
            continue
        if alan == "ntp_server":
            if not re.match(r"^[A-Za-z0-9.\-]+$", v):
                return (False, "ntp_server gecersiz", {})
        elif not _ipv4_gecerli(v):
            return (False, "%s gecersiz IPv4" % alan, {})
        temiz[alan] = v

    for alan in ("subnet_mask", "subnet_musk"):
        v = str(temiz.get(alan, "")).strip()
        if not v:
            continue
        if not _mask_gecerli(v):
            return (False, "%s gecersiz" % alan, {})
        temiz[alan] = v

    for alan in ("dns",):
        dns_ham = str(temiz.get(alan, "")).strip()
        if not dns_ham:
            continue
        dns_liste = [x.strip() for x in dns_ham.split(",") if x.strip()]
        if any(not _ipv4_gecerli(x) for x in dns_liste):
            return (False, "%s listesi gecersiz" % alan, {})
        temiz[alan] = ",".join(dns_liste)

    if "reboot_after_apply" in temiz:
        ok, sonuc = _bool_alan(temiz.get("reboot_after_apply"), "reboot_after_apply")
        if not ok:
            return (False, str(sonuc), {})
        temiz["reboot_after_apply"] = sonuc

    if "heartbeat_aktif" in temiz:
        ok, sonuc = _bool_alan(temiz.get("heartbeat_aktif"), "heartbeat_aktif")
        if not ok:
            return (False, str(sonuc), {})
        temiz["heartbeat_aktif"] = sonuc

    if "wifi_hidden" in temiz:
        ok, sonuc = _bool_alan(temiz.get("wifi_hidden"), "wifi_hidden")
        if not ok:
            return (False, str(sonuc), {})
        temiz["wifi_hidden"] = sonuc

    return (True, "", temiz)


def kaydet_config_payload(veri: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Donus: (ok, hata_mesaji, meta)
    meta: saved_fields, ignored_fields
    """
    if not isinstance(veri, dict):
        return (False, "json body nesne olmali", {})
    _, yoksayilan = normalize_sunucu_payload(veri)
    ok, hata, temiz = validate_config_payload(veri)
    if not ok:
        return (False, hata, {"ignored_fields": yoksayilan})
    try:
        mevcut = oku_config()
        if not isinstance(mevcut, dict):
            mevcut = {}
        mevcut.update(temiz)
        yaz_config(mevcut)
    except Exception as e:
        return (False, "config kaydedilemedi: %s" % e, {"ignored_fields": yoksayilan})
    return (
        True,
        "",
        {
            "saved_fields": sorted(temiz.keys()),
            "ignored_fields": yoksayilan,
        },
    )
