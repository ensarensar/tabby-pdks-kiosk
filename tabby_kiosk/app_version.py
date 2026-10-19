# -*- coding: utf-8 -*-
"""Kiosk uygulama surumu."""
from __future__ import annotations

import os

_PROJE_KOKU = os.path.dirname(os.path.abspath(__file__))
_VERSION_DOSYASI = os.path.join(_PROJE_KOKU, "VERSION")


def oku_uygulama_surumu() -> str:
    try:
        with open(_VERSION_DOSYASI, "r", encoding="utf-8") as f:
            surum = f.read().strip()
    except Exception:
        return "0.0.0"
    return surum or "0.0.0"
