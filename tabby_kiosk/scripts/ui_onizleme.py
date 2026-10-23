#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ekran onizleme (servis durdurulmusken): ui_onizleme.py <hazir|bekleme|giris|cikis|hata> [saniye]
Sahte QR ile cizer; ag istegi yapmaz."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tkinter as tk  # noqa: E402

import qr_ekran  # noqa: E402
from ui import KioskArayuz  # noqa: E402

durum = sys.argv[1] if len(sys.argv) > 1 else "hazir"
sure = float(sys.argv[2]) if len(sys.argv) > 2 else 6
kok = tk.Tk()
u = KioskArayuz(kok)
u._qr_taban_getir = lambda: ""
kok.update()
u._qr_uygula(qr_ekran.QrSonuc("ok", jeton="eyJvbml6bGVtZSI6MX0.T05JWkxFTUVfREVNT19RUl9KRVRPTlU", sonraki_s=3600))
if durum == "bekleme":
    u.bekleme_moduna_gec()
elif durum == "giris":
    u.islem_basarili_goster("Ensar Alemdaroğlu", "09:30", True)
elif durum == "cikis":
    u.islem_basarili_goster("Ensar Alemdaroğlu", "17:45", False)
elif durum == "hata":
    u.merkez_hata_goster("Sunucuya ulaşılamadı, kaydınız çevrimdışı alındı")
kok.after(int(sure * 1000), kok.destroy)
kok.mainloop()
