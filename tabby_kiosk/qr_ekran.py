# -*- coding: utf-8 -*-
"""
Kartini unutanlar icin ekranda dinamik QR (DEVICE_SPEC.md bolum 5 ve 10).

GET <servis_tabani>/tabby-kiosk-qr?cihaz=<id>  (cihaz sirri basliklariyla)
  200 {"ok":true,"jeton":"<b64(json)>.<b64(hmac)>","sureSaniye":10,"exp":...}
  403 QR bu cihaz icin kapali  -> QR gizlenir
  401 sir gecersiz/yok         -> QR gizlenir
Jeton ~10 sn yasar; yaklasik 8. saniyede yenisi istenir. QR icerigi jetonun
kendisidir; telefon (Kapi QR ekrani) bunu POST /api/mobil/kiosk/qr-kullan'a yollar.
"""
from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass
from typing import Callable, Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

import cihaz_kimlik

LOG = logging.getLogger(__name__)

VARSAYILAN_YENILE_S = 8.0
KAPALI_TEKRAR_S = 60.0
HATA_TEKRAR_S = 15.0
_TIMEOUT_S = 5.0


@dataclass
class QrSonuc:
    durum: str  # "ok" | "kapali" | "kimlik" | "hata" | "yapilandirilmamis"
    jeton: str = ""
    sonraki_s: float = VARSAYILAN_YENILE_S
    mesaj: str = ""


def qr_url(taban: str, cihaz: str) -> str:
    return "%s/tabby-kiosk-qr?%s" % (taban.rstrip("/"), urlparse.urlencode({"cihaz": cihaz}))


def yenileme_saniye(sure: object) -> float:
    try:
        s = float(sure)
    except (TypeError, ValueError):
        return VARSAYILAN_YENILE_S
    if s <= 0:
        return VARSAYILAN_YENILE_S
    return max(2.0, min(VARSAYILAN_YENILE_S, s * 0.8))


def _varsayilan_acici(req: urlrequest.Request, timeout: float):
    ctx = ssl._create_unverified_context()  # hastane ic sertifikasi self-signed
    return urlrequest.urlopen(req, timeout=timeout, context=ctx)


def jeton_iste(
    taban: str,
    acici: Optional[Callable[..., object]] = None,
) -> QrSonuc:
    cihaz, _ = cihaz_kimlik.oku_kimlik()
    if not taban or not cihaz:
        return QrSonuc("yapilandirilmamis", sonraki_s=KAPALI_TEKRAR_S)
    headers = cihaz_kimlik.basliklara_ekle({"Accept": "application/json"})
    req = urlrequest.Request(qr_url(taban, cihaz), headers=headers, method="GET")
    acici = acici or _varsayilan_acici
    try:
        with acici(req, timeout=_TIMEOUT_S) as resp:  # type: ignore[attr-defined]
            j = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
    except urlerror.HTTPError as e:
        if e.code == 403:
            return QrSonuc("kapali", sonraki_s=KAPALI_TEKRAR_S)
        if e.code == 401:
            return QrSonuc("kimlik", sonraki_s=KAPALI_TEKRAR_S, mesaj="Cihaz kimligi gecersiz")
        return QrSonuc("hata", sonraki_s=HATA_TEKRAR_S, mesaj="HTTP %s" % e.code)
    except Exception as e:
        return QrSonuc("hata", sonraki_s=HATA_TEKRAR_S, mesaj=str(e))
    jeton = str((j or {}).get("jeton") or "").strip() if isinstance(j, dict) else ""
    if not jeton or "." not in jeton:
        return QrSonuc("hata", sonraki_s=HATA_TEKRAR_S, mesaj="Gecersiz jeton")
    return QrSonuc("ok", jeton=jeton, sonraki_s=yenileme_saniye(j.get("sureSaniye")))


def qr_resmi(jeton: str, kenar_px: int):
    """PIL Image. qrcode kutuphanesi yoksa None."""
    try:
        import qrcode
    except Exception:
        LOG.warning("qrcode kutuphanesi yok; QR cizilemiyor")
        return None
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=4)
    qr.add_data(jeton)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((kenar_px, kenar_px))
