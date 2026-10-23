# -*- coding: utf-8 -*-
"""
Tabby kiosk icin kalici uygulama ayarlari (servis URL ve timeout).
Ayarlar `app_settings.json` dosyasindan okunur; yoksa varsayilanlar kullanilir.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import urlparse
from config_store import oku_config


_PROJE_KOKU = os.path.dirname(os.path.abspath(__file__))
_CONFIG_DIZINI = os.environ.get(
    "TABBY_CONFIG_DIR",
    os.path.join(os.path.expanduser("~"), ".config", "tabby-kiosk"),
)
_AYAR_DOSYASI = os.environ.get(
    "TABBY_APP_SETTINGS_FILE",
    os.path.join(_CONFIG_DIZINI, "app_settings.json"),
)
_ESKI_AYAR_DOSYASI = os.path.join(_PROJE_KOKU, "app_settings.json")


@dataclass
class UygulamaAyarlari:
    servis_url: str = "http://10.85.100.8:3000/tabby-kiosk-kartokuma"
    servis_timeout_s: float = 4.0


def _varsayilan() -> UygulamaAyarlari:
    return UygulamaAyarlari()


def _dogrula_url(url: str) -> str:
    u = (url or "").strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("Servis URL gecersiz. Ornek: http://10.85.100.8:3000/tabby-kiosk-kartokuma")
    return u


def oku_ayarlar() -> UygulamaAyarlari:
    d = _varsayilan()
    cfg = oku_config()
    if isinstance(cfg, dict):
        try:
            servis_url = _dogrula_url(str(cfg.get("servis_url", "")).strip())
        except ValueError:
            servis_url = ""
        timeout_ham = cfg.get("servis_timeout_s", "")
        timeout_s = d.servis_timeout_s
        if timeout_ham not in ("", None):
            try:
                timeout_s = float(timeout_ham)
            except (TypeError, ValueError):
                timeout_s = d.servis_timeout_s
            timeout_s = max(1.0, min(timeout_s, 30.0))
        if servis_url:
            return UygulamaAyarlari(servis_url=servis_url, servis_timeout_s=timeout_s)

    kaynak = _AYAR_DOSYASI
    if not os.path.isfile(kaynak) and os.path.isfile(_ESKI_AYAR_DOSYASI):
        kaynak = _ESKI_AYAR_DOSYASI
    if not os.path.isfile(kaynak):
        return d
    try:
        with open(kaynak, "r", encoding="utf-8") as f:
            ham: Dict[str, Any] = json.load(f)
    except Exception:
        return d

    try:
        servis_url = _dogrula_url(str(ham.get("servis_url", d.servis_url)))
    except ValueError:
        servis_url = d.servis_url

    try:
        timeout_s = float(ham.get("servis_timeout_s", d.servis_timeout_s))
    except (TypeError, ValueError):
        timeout_s = d.servis_timeout_s

    timeout_s = max(1.0, min(timeout_s, 30.0))
    return UygulamaAyarlari(servis_url=servis_url, servis_timeout_s=timeout_s)
