# -*- coding: utf-8 -*-
"""Tk ekran durumlari hata vermeden cizilir (TABBY_UI_TEST=1 ve ekran gerekir)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(os.environ.get("TABBY_UI_TEST") == "1", "TABBY_UI_TEST=1 degil")
class UiTest(unittest.TestCase):
    def test_durumlar(self):
        os.environ["TABBY_TAM_EKRAN"] = "0"
        import tkinter as tk
        import qr_ekran
        from ui import KioskArayuz

        kok = tk.Tk()
        kok.geometry("480x320")
        u = KioskArayuz(kok)
        u._qr_taban_getir = lambda: ""
        kok.update()
        u._qr_uygula(qr_ekran.QrSonuc("ok", jeton="a.b", sonraki_s=3600))
        self.assertTrue(u._qr_gorunur)
        u.bekleme_moduna_gec()
        self.assertTrue(u.bekleme_modunda_mi())
        u.islem_basarili_goster("Ad Soyad", "09:30", True)
        self.assertFalse(u.bekleme_modunda_mi())
        u.merkez_hata_goster("hata")
        u.islem_bekleniyor_goster(False)
        u.hazir_ekrana_gec()
        u._qr_uygula(qr_ekran.QrSonuc("kapali", sonraki_s=3600))
        self.assertFalse(u._qr_gorunur)
        kok.update()
        kok.destroy()


if __name__ == "__main__":
    unittest.main()
