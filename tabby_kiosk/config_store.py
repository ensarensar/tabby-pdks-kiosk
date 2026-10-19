# -*- coding: utf-8 -*-
"""
Tabby kiosk tek kaynak konfigurasyon dosyasi.

Birincil (reboot sonrasi kalici): /var/lib/tabby-kiosk/config.json
Ayna (uyumluluk): ~/.config/tabby-kiosk/config.json
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

LOG = logging.getLogger(__name__)

_FABRIKA_VARSAYILANLARI: Dict[str, Any] = {
    "cihaz_adi": "default-reader",
    "cihaz_ip": "172.16.32.50",
    "servis_url": "https://10.85.1.83:8000/tabby-kiosk-kartokuma",
    "heartbeat_url": "https://10.85.1.83:8000/api/pdks-cihazlari/tabby/heartbeat",
    "bekleme_video_login_url": "https://10.85.1.83:8000/api/oturum/giris",
    "heartbeat_aktif": True,
    "reboot_after_apply": False,
}

_KALICI_DIZIN = os.environ.get("TABBY_KALICI_CONFIG_DIR", "/var/lib/tabby-kiosk").strip()
_KALICI_DOSYA = os.environ.get(
    "TABBY_KALICI_CONFIG_FILE",
    os.path.join(_KALICI_DIZIN, "config.json"),
)


def _home_config_dizini() -> str:
    env = os.environ.get("TABBY_CONFIG_DIR", "").strip()
    if env:
        return env
    home = os.environ.get("HOME", "").strip()
    if home:
        return os.path.join(home, ".config", "tabby-kiosk")
    return "/home/tabby/.config/tabby-kiosk"


_HOME_DIZIN = _home_config_dizini()
_HOME_DOSYA = os.path.join(_HOME_DIZIN, "config.json")

# Geriye donuk: TABBY_CONFIG_FILE birincil dosyayi override eder.
_BIRINCIL_DOSYA = os.environ.get("TABBY_CONFIG_FILE", "").strip() or _KALICI_DOSYA
_AYNA_DOSYA = _HOME_DOSYA


def config_dosyasi() -> str:
    return _BIRINCIL_DOSYA


def yedek_config_dosyasi() -> str:
    return _AYNA_DOSYA


def fabrika_varsayilanlari() -> Dict[str, Any]:
    return dict(_FABRIKA_VARSAYILANLARI)


def _tabby_uid_gid() -> tuple[int, int] | None:
    try:
        import pwd

        kayit = pwd.getpwnam("tabby")
        return (kayit.pw_uid, kayit.pw_gid)
    except Exception:
        return None


def _sahiplik_tabby(yol: str) -> None:
    uid_gid = _tabby_uid_gid()
    if uid_gid is None:
        return
    uid, gid = uid_gid
    try:
        os.chown(yol, uid, gid)
    except Exception:
        pass


def _json_dosyaya_yaz(hedef: str, veri: Dict[str, Any]) -> None:
    dizin = os.path.dirname(hedef)
    os.makedirs(dizin, exist_ok=True)
    gecici = hedef + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(gecici, hedef)
    if os.geteuid() == 0:
        _sahiplik_tabby(hedef)
        try:
            _sahiplik_tabby(dizin)
        except Exception:
            pass


def _json_dosyadan_oku(yol: str) -> Dict[str, Any] | None:
    if not os.path.isfile(yol):
        return None
    try:
        with open(yol, "r", encoding="utf-8") as f:
            j = json.load(f)
    except Exception:
        return None
    return j if isinstance(j, dict) else None


def _aynalama_yap(veri: Dict[str, Any]) -> None:
    try:
        _json_dosyaya_yaz(_AYNA_DOSYA, veri)
    except Exception as e:
        LOG.warning("config aynasi yazilamadi (%s): %s", _AYNA_DOSYA, e)


def yaz_config(veri: Dict[str, Any]) -> None:
    if not isinstance(veri, dict):
        raise ValueError("config verisi nesne olmali")
    _json_dosyaya_yaz(_BIRINCIL_DOSYA, veri)
    _aynalama_yap(veri)
    LOG.info("config kaydedildi: %s", _BIRINCIL_DOSYA)


def oku_config() -> Dict[str, Any]:
    j = _json_dosyadan_oku(_BIRINCIL_DOSYA)
    if j is None:
        j = _json_dosyadan_oku(_AYNA_DOSYA)
        if j is not None:
            try:
                _json_dosyaya_yaz(_BIRINCIL_DOSYA, j)
                LOG.warning(
                    "config birincil dosyada yoktu; aynadan geri yuklendi: %s",
                    _AYNA_DOSYA,
                )
            except Exception as e:
                LOG.error("config birincil dosyaya yazilamadi: %s", e)
    if j is None:
        try:
            yaz_config(fabrika_varsayilanlari())
        except Exception:
            return fabrika_varsayilanlari()
        return fabrika_varsayilanlari()
    birlesik = fabrika_varsayilanlari()
    birlesik.update(j)
    return birlesik
