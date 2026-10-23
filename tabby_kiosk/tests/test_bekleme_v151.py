# -*- coding: utf-8 -*-
"""v1.5.1: periyodik durum_guncelle bekleme ekranini (QR + tabby) kapatmamali."""
import os
import re
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BeklemeKalicilikTest(unittest.TestCase):
    def test_durum_guncelle_bekleme_korumasi(self):
        src = open(os.path.join(KOK, "main.py"), encoding="utf-8").read()
        govde = src.split("def durum_guncelle()", 1)[1].split("def durum_zamanlamasi()", 1)[0]
        koruma = govde.find("uygulama.bekleme_modunda_mi()")
        hazir = govde.rfind("uygulama.hazir_ekrana_gec()")
        self.assertNotEqual(koruma, -1, "bekleme korumasi yok")
        self.assertLess(koruma, hazir, "koruma hazir_ekrana_gec'ten once olmali")
        self.assertTrue(re.search(r"if not aktif_hata_metni and uygulama\.bekleme_modunda_mi\(\):\s*return", govde))


if __name__ == "__main__":
    unittest.main()
