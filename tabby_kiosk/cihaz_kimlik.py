# -*- coding: utf-8 -*-
"""
Cihaz kimligi ve sirri (DEVICE_SPEC.md bolum 1).

Her sunucu istegi iki baslik tasir:
  X-Tabby-Cihaz        cihaz kimligi (or. K1)
  X-Tabby-Cihaz-Gizli  kurulumda POST /api/mobil/kiosk/cihaz yanitinda bir kez verilen sir

Kaynak sirasi:
  1) Ortam: TABBY_CIHAZ_ID ve TABBY_CIHAZ_GIZLI
  2) Dosya: TABBY_CIHAZ_KIMLIK_DOSYA, yoksa /var/lib/tabby-kiosk/cihaz_kimlik.json
     {"cihaz": "K1", "gizli": "..."}   (chmod 600, depoya girmez)

Sir kaynak kodda yoktur. Sir yoksa baslik eklenmez; sunucu eski uc / allowlist
moduna duser (yalniz izin verilmisse).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Dict, Optional, Tuple

LOG = logging.getLogger(__name__)

VARSAYILAN_DOSYA = "/var/lib/tabby-kiosk/cihaz_kimlik.json"
BASLIK_CIHAZ = "X-Tabby-Cihaz"
BASLIK_GIZLI = "X-Tabby-Cihaz-Gizli"

_kilit = threading.Lock()
_onbellek: Dict[str, object] = {"yol": "", "mtime": None, "deger": ("", "")}


def kimlik_dosyasi() -> str:
    return os.environ.get("TABBY_CIHAZ_KIMLIK_DOSYA", "").strip() or VARSAYILAN_DOSYA


def _dosyadan_oku(yol: str) -> Tuple[str, str]:
    try:
        mtime = os.path.getmtime(yol)
    except OSError:
        return ("", "")
    with _kilit:
        if _onbellek["yol"] == yol and _onbellek["mtime"] == mtime:
            return _onbellek["deger"]  # type: ignore[return-value]
    try:
        with open(yol, "r", encoding="utf-8") as f:
            j = json.load(f)
    except Exception as e:
        LOG.warning("Cihaz kimlik dosyasi okunamadi (%s): %s", yol, e)
        return ("", "")
    if not isinstance(j, dict):
        return ("", "")
    cihaz = str(j.get("cihaz") or j.get("cihaz_id") or "").strip()
    gizli = str(j.get("gizli") or "").strip()
    deger = (cihaz, gizli)
    with _kilit:
        _onbellek.update({"yol": yol, "mtime": mtime, "deger": deger})
    return deger


def oku_kimlik() -> Tuple[str, str]:
    """(cihaz, gizli). Ikisi birden yoksa ("", "")."""
    cihaz = os.environ.get("TABBY_CIHAZ_ID", "").strip()
    gizli = os.environ.get("TABBY_CIHAZ_GIZLI", "").strip()
    if cihaz and gizli:
        return (cihaz, gizli)
    d_cihaz, d_gizli = _dosyadan_oku(kimlik_dosyasi())
    cihaz = cihaz or d_cihaz
    gizli = gizli or d_gizli
    if not cihaz or not gizli:
        return ("", "")
    return (cihaz, gizli)


def cihaz_id() -> Optional[str]:
    c, _ = oku_kimlik()
    return c or None


def kimlik_basliklari() -> Dict[str, str]:
    cihaz, gizli = oku_kimlik()
    if not cihaz or not gizli:
        return {}
    return {BASLIK_CIHAZ: cihaz, BASLIK_GIZLI: gizli}


def basliklara_ekle(headers: Dict[str, str]) -> Dict[str, str]:
    headers.update(kimlik_basliklari())
    return headers
