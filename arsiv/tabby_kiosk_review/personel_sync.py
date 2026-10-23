# -*- coding: utf-8 -*-
"""Sunucudan personel senkronu ve kart kuyrugu flush."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Tuple
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from app_settings import oku_ayarlar
from config_store import oku_config
from device_info import oku_cihaz_bilgisi
import offline_db

LOG = logging.getLogger(__name__)

_VARSAYILAN_CHUNK = 500
_HTTP_TIMEOUT_S = 30.0


def _cfg() -> Dict[str, Any]:
    cfg = oku_config()
    return cfg if isinstance(cfg, dict) else {}


def _cihaz_mac() -> str:
    return str(oku_cihaz_bilgisi().cihaz_mac or "").strip().upper()


def _chunk_boyutu() -> int:
    try:
        return max(50, min(int(_cfg().get("personel_sync_chunk", _VARSAYILAN_CHUNK)), 2000))
    except (TypeError, ValueError):
        return _VARSAYILAN_CHUNK


def _servis_tabani() -> str:
    ayar = oku_ayarlar()
    parsed = urlparse.urlparse(ayar.servis_url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return "%s://%s" % (parsed.scheme, parsed.netloc)
    ozel = str(_cfg().get("personel_export_url", "")).strip()
    if ozel:
        p = urlparse.urlparse(ozel)
        if p.scheme in ("http", "https") and p.netloc:
            return "%s://%s" % (p.scheme, p.netloc)
    return ""


def personel_export_url() -> str:
    ozel = str(_cfg().get("personel_export_url", "")).strip()
    if ozel:
        return ozel
    taban = _servis_tabani()
    if not taban:
        return ""
    return "%s/tabby-kiosk-personel-export" % taban


def toplu_kart_url() -> str:
    ozel = str(_cfg().get("kart_toplu_url", "")).strip()
    if ozel:
        return ozel
    taban = _servis_tabani()
    if not taban:
        return ""
    return "%s/tabby-kiosk-kartokuma-toplu" % taban


def _json_istek(
    url: str,
    *,
    method: str = "GET",
    body: Dict[str, Any] | None = None,
    timeout_s: float = _HTTP_TIMEOUT_S,
) -> Tuple[bool, Dict[str, Any], str]:
    if not url:
        return (False, {}, "URL bos")
    headers = {"Accept": "application/json"}
    mac = _cihaz_mac()
    if mac:
        headers["X-Tabby-Device-Mac"] = mac
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers=headers, method=method)
    try:
        with urlrequest.urlopen(req, timeout=timeout_s) as resp:
            ham = resp.read().decode("utf-8", errors="ignore").strip()
            try:
                j = json.loads(ham or "{}")
            except ValueError:
                j = {}
            if not isinstance(j, dict):
                j = {}
            return (True, j, "")
    except urlerror.HTTPError as e:
        detay = e.read().decode("utf-8", errors="ignore").strip()
        return (False, {}, "HTTP %s %s" % (e.code, detay[:300]))
    except Exception as e:
        return (False, {}, str(e))


def personel_senkronize(tam_yenile: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
    offline_db.veritabani_hazirla()
    export_url = personel_export_url()
    if not export_url:
        return (False, "personel_export_url turetilemedi", {})

    if tam_yenile:
        offline_db.personel_temizle()

    chunk = _chunk_boyutu()
    sayfa = 1
    toplam = 0
    while True:
        ayrac = "&" if "?" in export_url else "?"
        url = "%s%spage=%s&limit=%s" % (export_url, ayrac, sayfa, chunk)
        ok, yanit, hata = _json_istek(url)
        if not ok:
            return (False, hata or "personel export basarisiz", {"toplam": toplam, "sayfa": sayfa})

        kayitlar = yanit.get("data") or yanit.get("personeller") or []
        if not isinstance(kayitlar, list):
            kayitlar = []
        yazilan = offline_db.personel_toplu_yaz(kayitlar)
        toplam += yazilan

        has_more = bool(yanit.get("hasMore"))
        if not has_more:
            if yazilan == 0 and sayfa == 1:
                break
            if yazilan < chunk:
                break
        if yazilan == 0:
            break
        sayfa += 1
        if sayfa > 5000:
            break

    simdi = datetime.now().isoformat(timespec="seconds")
    metin = "%s kayit, %s" % (toplam, simdi)
    offline_db.meta_yaz("son_personel_sync", simdi)
    offline_db.meta_yaz("son_personel_sync_metni", metin)
    LOG.info("Personel senkronu tamamlandi: %s", metin)
    return (
        True,
        "",
        {
            "personel_sayisi": offline_db.personel_sayisi(),
            "son_sync": simdi,
            "son_sync_metni": metin,
        },
    )


def kuyruk_flush(chunk: int = 50) -> Tuple[bool, str, Dict[str, Any]]:
    offline_db.veritabani_hazirla()
    url = toplu_kart_url()
    if not url:
        return (False, "kart_toplu_url turetilemedi", {})

    bekleyen = offline_db.bekleyen_kuyruk(chunk)
    if not bekleyen:
        return (True, "", {"gonderilen": 0, "kalan": 0})

    kayitlar = []
    idler = []
    for oge in bekleyen:
        kuyruk_id = oge.get("_kuyruk_id")
        payload = {k: v for k, v in oge.items() if k != "_kuyruk_id"}
        if kuyruk_id is not None:
            idler.append((int(kuyruk_id), payload))
        kayitlar.append(payload)

    ok, yanit, hata = _json_istek(url, method="POST", body={"kayitlar": kayitlar}, timeout_s=60.0)
    if not ok:
        for kid, _ in idler:
            offline_db.kuyruk_isaretle_hata(kid, hata)
        return (False, hata, {"denenen": len(kayitlar)})

    sonuclar = yanit.get("results") or yanit.get("sonuclar") or []
    basarili = 0
    if isinstance(sonuclar, list) and len(sonuclar) == len(idler):
        for idx, (kid, _) in enumerate(idler):
            item = sonuclar[idx] if idx < len(sonuclar) else {}
            item_ok = bool((item or {}).get("ok", (item or {}).get("success", False)))
            if item_ok:
                offline_db.kuyruk_isaretle_gonderildi(kid)
                basarili += 1
            else:
                offline_db.kuyruk_isaretle_hata(
                    kid,
                    str((item or {}).get("message") or (item or {}).get("error") or "gonderilemedi"),
                )
    else:
        # Toplu basarili kabul et
        if yanit.get("ok", True):
            for kid, _ in idler:
                offline_db.kuyruk_isaretle_gonderildi(kid)
            basarili = len(idler)

    simdi = datetime.now().isoformat(timespec="seconds")
    offline_db.meta_yaz("son_kuyruk_flush", simdi)
    kalan = offline_db.bekleyen_kuyruk_sayisi()
    offline_db.meta_yaz("son_kuyruk_flush_gonderilen", str(basarili))
    offline_db.meta_yaz("son_kuyruk_flush_kalan", str(kalan))
    return (
        True,
        "",
        {
            "gonderilen": basarili,
            "denenen": len(kayitlar),
            "kalan": kalan,
            "son_flush": simdi,
            "gonderilen_kuyruk_toplam": offline_db.gonderilen_kuyruk_sayisi(),
        },
    )


def personel_durum_yaniti() -> Dict[str, Any]:
    ozet = offline_db.durum_ozeti()
    return {
        "ok": True,
        "personel_sayisi": ozet["personel_sayisi"],
        "personelSayisi": ozet["personel_sayisi"],
        "bekleyen_kuyruk": ozet["bekleyen_kuyruk"],
        "bekleyenKuyruk": ozet["bekleyen_kuyruk"],
        "gonderilen_kuyruk": ozet["gonderilen_kuyruk"],
        "gonderilenKuyruk": ozet["gonderilen_kuyruk"],
        "son_kuyruk_gonderilen": ozet["son_flush_gonderilen"],
        "sonKuyrukGonderilen": ozet["son_flush_gonderilen"],
        "son_kuyruk_kalan": ozet["son_flush_kalan"],
        "sonKuyrukKalan": ozet["son_flush_kalan"],
        "son_sync": ozet["son_sync"],
        "son_sync_metni": ozet["son_sync_metni"],
        "sonPersonelSyncMetni": ozet["son_sync_metni"],
        "son_flush": ozet["son_flush"],
        "sonKuyrukFlush": ozet["son_flush"],
        "son_flush_neden": ozet["son_flush_neden"],
    }


def cache_temizle(kart_kuyrugunu_temizle: bool = False) -> Dict[str, Any]:
    silinen_personel = offline_db.personel_temizle()
    silinen_kuyruk = 0
    if kart_kuyrugunu_temizle:
        silinen_kuyruk = offline_db.kuyruk_temizle(gonderilmis=False)
    else:
        silinen_kuyruk = offline_db.kuyruk_temizle(gonderilmis=True)
    return {
        "ok": True,
        "silinen_personel": silinen_personel,
        "silinen_kuyruk": silinen_kuyruk,
        **personel_durum_yaniti(),
    }
