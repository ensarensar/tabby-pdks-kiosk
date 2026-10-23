# -*- coding: utf-8 -*-
"""Online/offline kart okuma akisi."""
from __future__ import annotations

import cihaz_kimlik
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest

from app_settings import oku_ayarlar
from device_info import oku_cihaz_bilgisi
import offline_db

LOG = logging.getLogger(__name__)


def _json_metin_al(j: dict, adaylar: tuple[str, ...], varsayilan: str = "") -> str:
    for anahtar in adaylar:
        v = j.get(anahtar)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return varsayilan


def _offline_mesaj_uret(personel: Dict[str, str], is_giris: bool, zaman: str) -> str:
    ad = ("%s %s" % (personel.get("isim", ""), personel.get("soyisim", ""))).strip()
    try:
        saat = datetime.fromisoformat(zaman).strftime("%H:%M")
    except Exception:
        saat = datetime.now().strftime("%H:%M")
    etiket = "Giriş" if is_giris else "Çıkış"
    return "Sn %s %s Kaydınız %s ile kaydedilmiştir. (Offline)" % (ad, etiket, saat)


def _sunucuya_gonder(payload: Dict[str, Any]) -> Tuple[bool, str, bool, str, str, bool]:
    """
    Donus: ok, mesaj, is_giris, ad_soyad, saat, sunucuya_gitti_mi
    """
    ayar = oku_ayarlar()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        ayar.servis_url,
        data=body,
        headers=cihaz_kimlik.basliklara_ekle({"Content-Type": "application/json"}),
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=ayar.servis_timeout_s) as resp:
            ham = resp.read().decode("utf-8", errors="ignore").strip()
            if not ham:
                return (True, "", True, "Kullanici", datetime.now().strftime("%H:%M"), True)
            try:
                j = json.loads(ham)
            except ValueError:
                return (True, ham, True, "Kullanici", datetime.now().strftime("%H:%M"), True)
    except urlerror.HTTPError as e:
        detay = e.read().decode("utf-8", errors="ignore").strip()
        return (False, "Sunucu HTTP hatasi: %s %s" % (e.code, detay), True, "", "", False)
    except Exception as e:
        return (False, "Sunucuya baglanilamadi: %s" % e, True, "", "", False)

    basarili = bool(j.get("success", j.get("ok", True)))
    if not basarili:
        msg = _json_metin_al(j, ("message", "mesaj", "error", "hata", "detail", "detay"), "Islem basarisiz")
        return (False, msg, True, "", "", False)

    yon = str(j.get("yon", j.get("direction", ""))).strip().lower()
    if yon in ("giris", "in", "entry"):
        is_giris = True
    elif yon in ("cikis", "out", "exit"):
        is_giris = False
    else:
        is_giris = str(payload.get("yon", "")).strip().lower() != "cikis"

    ad = _json_metin_al(
        j,
        ("ad_soyad", "full_name", "fullName", "name", "person", "kullanici", "display_name", "displayName"),
        "",
    )
    if not ad and isinstance(j.get("data"), dict):
        ad = _json_metin_al(
            j.get("data") or {},
            ("ad_soyad", "full_name", "fullName", "name", "person", "kullanici", "display_name", "displayName"),
            "",
        )
    saat = _json_metin_al(j, ("saat", "time", "islem_saati"), datetime.now().strftime("%H:%M"))
    msg = _json_metin_al(j, ("message", "mesaj", "metin"), "")
    if not msg and isinstance(j.get("data"), dict):
        msg = _json_metin_al(j.get("data") or {}, ("message", "mesaj", "metin"), "")
    return (True, msg, is_giris, ad or "Kullanici", saat, True)


def kart_okuma_isle(
    oge: Dict[str, Any],
    varsayilan_giris_mi: bool,
    online_mi: Callable[[], bool],
) -> Tuple[bool, str, bool, str, str]:
    """
    Donus: ok, mesaj, is_giris, ad_soyad, saat
    """
    offline_db.veritabani_hazirla()
    payload = {
        "kart_numarasi": str(oge.get("kart_numarasi", "")).strip(),
        "okuyucu_adi": str(oge.get("okuyucu_adi", "")).strip(),
        "okuyucu_kisa": str(oge.get("okuyucu_kisa", "")).strip(),
        "usb_port": oge.get("usb_port"),
        "yon": "giris" if varsayilan_giris_mi else "cikis",
        "zaman": datetime.now().isoformat(timespec="seconds"),
    }
    payload.update(oku_cihaz_bilgisi().payload_dict())

    if online_mi():
        ok, msg, is_giris, ad, saat, sunucu = _sunucuya_gonder(payload)
        if ok and sunucu:
            return (ok, msg, is_giris, ad, saat)
        LOG.warning("Sunucu kart gonderimi basarisiz, offline dene: %s", msg)

    personel = offline_db.personel_bul_kart(payload["kart_numarasi"])
    if not personel:
        if offline_db.personel_sayisi() <= 0:
            return (
                False,
                "Offline mod: personel listesi bos. Once personel senkronu yapin.",
                varsayilan_giris_mi,
                "",
                "",
            )
        return (
            False,
            "Kart Basim Birimi Ile Goruserek Kart Numaranizi Kontrol ettiriniz",
            varsayilan_giris_mi,
            "",
            "",
        )

    offline_db.kuyruga_ekle(payload)
    is_giris = varsayilan_giris_mi
    ad = ("%s %s" % (personel.get("isim", ""), personel.get("soyisim", ""))).strip() or "Kullanici"
    msg = _offline_mesaj_uret(personel, is_giris, payload["zaman"])
    saat = datetime.now().strftime("%H:%M")
    return (True, msg, is_giris, ad, saat)
