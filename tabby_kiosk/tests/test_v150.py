# -*- coding: utf-8 -*-
"""v1.5.0: cihaz sirri basliklari ve QR ekrani. Ag ve cihaz gerektirmez."""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from urllib import error as urlerror

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cihaz_kimlik  # noqa: E402
import qr_ekran  # noqa: E402


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _temiz_env(**ek):
    env = {k: v for k, v in os.environ.items() if not k.startswith("TABBY_CIHAZ")}
    env["TABBY_CIHAZ_KIMLIK_DOSYA"] = "/nonexistent/x.json"
    env.update(ek)
    return mock.patch.dict(os.environ, env, clear=True)


class KimlikTest(unittest.TestCase):
    def test_env(self):
        with _temiz_env(TABBY_CIHAZ_ID="K1", TABBY_CIHAZ_GIZLI="s3"):
            self.assertEqual(
                cihaz_kimlik.kimlik_basliklari(),
                {"X-Tabby-Cihaz": "K1", "X-Tabby-Cihaz-Gizli": "s3"},
            )

    def test_dosya(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"cihaz": "K7", "gizli": "abc"}, f)
        try:
            with _temiz_env(TABBY_CIHAZ_KIMLIK_DOSYA=f.name):
                self.assertEqual(cihaz_kimlik.oku_kimlik(), ("K7", "abc"))
        finally:
            os.unlink(f.name)

    def test_sir_yoksa_baslik_yok(self):
        with _temiz_env(TABBY_CIHAZ_ID="K1"):
            self.assertEqual(cihaz_kimlik.kimlik_basliklari(), {})


class QrTest(unittest.TestCase):
    def _iste(self, acici):
        with _temiz_env(TABBY_CIHAZ_ID="K1", TABBY_CIHAZ_GIZLI="s3"):
            return qr_ekran.jeton_iste("https://10.85.1.83:8000", acici=acici)

    def test_ok_ve_basliklar(self):
        gorulen = {}

        def acici(req, timeout):
            gorulen["url"] = req.full_url
            gorulen["h"] = {k.lower(): v for k, v in req.header_items()}
            return _Yanit(json.dumps({"ok": True, "jeton": "aGVq.aW16YQ==", "sureSaniye": 10}).encode())

        s = self._iste(acici)
        self.assertEqual(s.durum, "ok")
        self.assertEqual(s.jeton, "aGVq.aW16YQ==")
        self.assertEqual(s.sonraki_s, 8.0)
        self.assertEqual(gorulen["url"], "https://10.85.1.83:8000/tabby-kiosk-qr?cihaz=K1")
        self.assertEqual(gorulen["h"]["x-tabby-cihaz"], "K1")
        self.assertEqual(gorulen["h"]["x-tabby-cihaz-gizli"], "s3")

    def _hata(self, kod):
        def acici(req, timeout):
            raise urlerror.HTTPError(req.full_url, kod, "x", {}, io.BytesIO(b"{}"))
        return acici

    def test_403_gizle(self):
        self.assertEqual(self._iste(self._hata(403)).durum, "kapali")

    def test_401_gizle(self):
        self.assertEqual(self._iste(self._hata(401)).durum, "kimlik")

    def test_yapilandirilmamis(self):
        with _temiz_env():
            self.assertEqual(qr_ekran.jeton_iste("https://x").durum, "yapilandirilmamis")

    def test_yenileme(self):
        self.assertEqual(qr_ekran.yenileme_saniye(10), 8.0)
        self.assertEqual(qr_ekran.yenileme_saniye(None), 8.0)
        self.assertEqual(qr_ekran.yenileme_saniye(1), 2.0)

    def test_sunucu_jetonu_telefonda_gecerli_bicim(self):
        """Sunucu qr_uret bicimi: b64url(json).b64url(hmac-sha256(sir, json))."""
        import base64, hashlib, hmac
        ham = json.dumps({"cihaz": "K1", "exp": 1.0, "hastane": "izmir", "nonce": "n"},
                         separators=(",", ":"), sort_keys=True).encode()
        imza = hmac.new(b"s3", ham, hashlib.sha256).digest()
        jeton = base64.urlsafe_b64encode(ham).decode() + "." + base64.urlsafe_b64encode(imza).decode()
        s = self._iste(lambda req, timeout: _Yanit(json.dumps({"ok": True, "jeton": jeton, "sureSaniye": 10}).encode()))
        self.assertEqual(s.jeton, jeton)  # QR icerigi degistirilmeden jetonun kendisi

    def test_qr_resmi(self):
        try:
            import qrcode  # noqa: F401
        except ImportError:
            self.skipTest("qrcode yok")
        img = qr_ekran.qr_resmi("aGVq.aW16YQ==", 150)
        self.assertEqual(img.size, (150, 150))


if __name__ == "__main__":
    unittest.main()
