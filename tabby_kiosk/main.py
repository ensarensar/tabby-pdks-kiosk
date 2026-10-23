# -*- coding: utf-8 -*-
"""
Tabby Kiosk giris noktasi: tam ekran UI ve USB okuyucu izleme.
"""
from __future__ import annotations

import ssl

# Hastane ic sertifikasi self-signed; urllib varsayilan dogrulama baglantiyi dusurur.
ssl._create_default_https_context = ssl._create_unverified_context

import logging
import logging.handlers
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlparse

from app_settings import oku_ayarlar
from config import (
    BEKLEME_VIDEO_BASLAMA_SANIYE,
    CIKIS_USB_PORT,
    GIRIS_USB_PORT,
    ISLEM_MESAJ_GOSTERIM_SANIYE,
    KIOSK_PENCERE_USTTE,
    OKUYUCU_YENIDEN_TARAMA_SANIYE,
)
from config_payload import kaydet_config_payload
from config_store import config_dosyasi, oku_config, yaz_config
from heartbeat import HeartbeatServisi
from offline_kart import kart_okuma_isle
from offline_servisi import OfflineServisi
from okuyucu_izleyici import OkuyucuIzleyici, kuyruk_tuketici
from standby_video import BeklemeVideoOynatici, bekleme_video_url_uret
from ui import KioskArayuz
from udev_yardimcisi import udev_izleme_baslat
from usb_aygitlari import okuyucu_aygitlarini_listele

LOG = logging.getLogger(__name__)
_PROJE_KOKU = os.path.dirname(os.path.abspath(__file__))
_CONFIG_DOSYASI = config_dosyasi()


def _log_yapilandir() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dosyasi = os.environ.get(
        "TABBY_LOG_FILE",
        os.path.join(os.path.expanduser("~"), ".config", "tabby-kiosk", "kiosk.log"),
    ).strip()
    if log_dosyasi:
        try:
            os.makedirs(os.path.dirname(log_dosyasi), exist_ok=True)
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    log_dosyasi, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
                )
            )
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _bool_env(anahtar: str, varsayilan: bool) -> bool:
    ham = os.environ.get(anahtar)
    if ham is None:
        return varsayilan
    return ham.strip().lower() in ("1", "true", "yes", "on")


def _reboot_tetikle() -> tuple[bool, str]:
    komutlar = [
        ["/usr/bin/sudo", "-n", "/bin/systemctl", "start", "tabby-remote-restart.service"],
        ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "tabby-remote-restart.service"],
        ["/usr/bin/sudo", "-n", "/usr/sbin/reboot"],
    ]
    for komut in komutlar:
        try:
            p = subprocess.run(
                komut,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=4,
                check=False,
            )
        except Exception as e:
            return (False, "Komut calisamadi: %s" % e)
        if p.returncode == 0:
            LOG.warning("Uzaktan reboot tetiklendi: %s", " ".join(komut))
            return (True, "")
    return (False, "Reboot yetkisi yok (sudo/systemctl ayari gerekli)")


def _apply_config_tetikle() -> tuple[bool, str]:
    apply_script = os.environ.get(
        "TABBY_APPLY_SCRIPT",
        os.path.join(_PROJE_KOKU, "scripts", "apply_tabby_config.sh"),
    )
    komutlar = [
        ["/usr/bin/sudo", "-n", "/bin/systemctl", "start", "tabby-apply-config.service"],
        ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "tabby-apply-config.service"],
        ["/bin/bash", apply_script],
    ]
    son_hata = ""
    for komut in komutlar:
        try:
            p = subprocess.run(
                komut,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=130,
                check=False,
            )
        except Exception as e:
            son_hata = "Apply komutu calisamadi: %s" % e
            continue
        if p.returncode == 0:
            LOG.info("Config apply tetiklendi: %s", " ".join(komut))
            return (True, "")
        son_hata = (p.stderr or p.stdout or "").strip() or "apply basarisiz"
    return (False, son_hata)


def _tabby_config_kaydet(veri: dict) -> tuple[bool, str]:
    ok, hata, _meta = kaydet_config_payload(veri)
    if not ok:
        return (ok, hata)
    apply_ok, apply_hata = _apply_config_tetikle()
    if not apply_ok:
        return (False, "config kaydedildi ama ag ayarlari uygulanamadi: %s" % apply_hata)
    return (True, "")


def _uzaktan_restart_sunucusu_baslat() -> None:
    if not _bool_env("TABBY_REMOTE_RESTART_ENABLE", False):
        LOG.info("Uzaktan restart endpoint'i kapali.")
        return
    host = os.environ.get("TABBY_REMOTE_RESTART_HOST", "0.0.0.0").strip() or "0.0.0.0"
    try:
        port = int(os.environ.get("TABBY_REMOTE_RESTART_PORT", "8081"))
    except ValueError:
        port = 8081

    class _Handler(BaseHTTPRequestHandler):
        def _json_oku(self) -> dict:
            try:
                boyut = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                boyut = 0
            ham = self.rfile.read(max(0, boyut)).decode("utf-8", errors="ignore")
            try:
                return json.loads(ham or "{}")
            except ValueError:
                return {}

        def _config_handle(self) -> None:
            j = self._json_oku()
            ok, hata = _tabby_config_kaydet(j)
            if not ok:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                govde = json.dumps({"ok": False, "error": hata}, ensure_ascii=False).encode(
                    "utf-8"
                )
                self.wfile.write(govde)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            govde = json.dumps(
                {
                    "ok": True,
                    "message": "config kaydedildi ve ag ayarlari uygulandi",
                    "config_file": _CONFIG_DOSYASI,
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.wfile.write(govde)

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/restart", "/tabby-config"):
                self.send_response(404)
                self.end_headers()
                return
            if self.path == "/restart":
                j = self._json_oku()
                if str(j.get("message", "")).strip() != "tabby-restart":
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":false,"error":"gecersiz mesaj"}')
                    return
                ok, hata = _reboot_tetikle()
                if ok:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true,"message":"restart tetiklendi"}')
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    govde = json.dumps(
                        {"ok": False, "error": hata}, ensure_ascii=False
                    ).encode("utf-8")
                    self.wfile.write(govde)
                return

            self._config_handle()

        def do_PUT(self) -> None:  # noqa: N802
            if self.path != "/tabby-config":
                self.send_response(404)
                self.end_headers()
                return
            self._config_handle()

        def log_message(self, _fmt: str, *_args) -> None:
            return

    try:
        sunucu = ThreadingHTTPServer((host, port), _Handler)
    except Exception as e:
        LOG.error("Uzaktan restart endpoint'i acilamadi %s:%s: %s", host, port, e)
        return
    LOG.info("Uzaktan restart endpoint'i aktif: http://%s:%s/restart", host, port)
    threading.Thread(target=sunucu.serve_forever, name="remote-restart-http", daemon=True).start()


def main() -> None:
    _log_yapilandir()
    _uzaktan_restart_sunucusu_baslat()
    heartbeat_servisi = HeartbeatServisi()
    heartbeat_servisi.baslat()

    if not os.environ.get("DISPLAY") and sys.platform != "darwin":
        os.environ.setdefault("DISPLAY", ":0")

    sonuc_kuyrugu: "queue.Queue[dict]" = queue.Queue()
    arayuz_kok = tk.Tk()

    try:
        uygulama = KioskArayuz(arayuz_kok)
    except tk.TclError as e:
        LOG.error("Tk baslatilamadi: %s", e)
        sys.exit(1)

    if os.environ.get("TABBY_QR_EKRAN", "1") not in ("0", "false", "hayir"):
        try:
            from personel_sync import _servis_tabani

            uygulama.qr_paneli_baslat(_servis_tabani)
        except Exception as e:
            LOG.warning("QR paneli baslatilamadi: %s", e)

    izleyici = OkuyucuIzleyici(sonuc_kuyrugu)
    udev_dur = threading.Event()
    mesaj_kilit_s = ISLEM_MESAJ_GOSTERIM_SANIYE
    ag_kontrol_acik = os.environ.get("TABBY_NETWORK_KONTROL", "1") not in (
        "0",
        "false",
        "False",
    )
    ag_yeniden_baglanma_aralik_s = 10.0

    bagli_portlar: set[int] = set()
    aktif_hata_metni = ""
    asama_after_id: Optional[str] = None
    hazir_after_id: Optional[str] = None
    bekleme_video_after_id: Optional[str] = None
    bekleme_video = BeklemeVideoOynatici()
    mesaj_gosterime_kadar = 0.0
    ag_durumu = {"son_kontrol": 0.0, "bagli": True}
    son_ag_yeniden_baglanma = 0.0
    ag_yeniden_baglanma_calismada = False
    okuma_isleniyor = False

    def _ag_yeniden_baglan_thread() -> None:
        nonlocal ag_yeniden_baglanma_calismada
        failover = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "scripts",
            "tabby_network_failover.sh",
        )
        if os.path.isfile(failover) and os.access(failover, os.X_OK):
            try:
                p = subprocess.run(
                    [failover, "once"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    check=False,
                    env={
                        **os.environ,
                        "TABBY_ETH_BEKLEME_S": os.environ.get("TABBY_ETH_BEKLEME_S", "15"),
                    },
                )
                if p.returncode == 0:
                    LOG.info("Ag failover scripti basarili")
                else:
                    LOG.warning(
                        "Ag failover scripti hata: %s",
                        (p.stderr or p.stdout or "").strip()[:300],
                    )
            except Exception:
                LOG.exception("Ag failover scripti calistirilamadi")
        else:
            try:
                p = subprocess.run(
                    ["nmcli", "networking", "on"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=4,
                    check=False,
                )
                if p.returncode == 0:
                    LOG.info("Ag yeniden baglanma: nmcli networking on")
            except Exception:
                LOG.debug("Ag yeniden baglanma atlandi")
        ag_yeniden_baglanma_calismada = False

    def _ag_yeniden_baglan_tetikle(simdi: float) -> None:
        nonlocal son_ag_yeniden_baglanma, ag_yeniden_baglanma_calismada
        if ag_yeniden_baglanma_calismada:
            return
        if (simdi - son_ag_yeniden_baglanma) < ag_yeniden_baglanma_aralik_s:
            return
        son_ag_yeniden_baglanma = simdi
        ag_yeniden_baglanma_calismada = True
        threading.Thread(
            target=_ag_yeniden_baglan_thread,
            name="ag-yeniden-baglan",
            daemon=True,
        ).start()
        LOG.warning(
            "Ag baglantisi kesik gorunuyor, yeniden baglanma denemesi baslatildi."
        )

    def _ag_bagli_mi() -> bool:
        if not ag_kontrol_acik:
            return True
        simdi = time.time()
        if (simdi - ag_durumu["son_kontrol"]) < 3.0:
            return bool(ag_durumu["bagli"])
        ag_durumu["son_kontrol"] = simdi
        ayar = oku_ayarlar()
        parsed = urlparse(ayar.servis_url)
        ag_hedef = os.environ.get("TABBY_NETWORK_HEDEF", parsed.hostname or "10.85.100.8").strip() or (parsed.hostname or "10.85.100.8")
        try:
            varsayilan_port = parsed.port or (443 if parsed.scheme == "https" else 3000)
            ag_port = int(os.environ.get("TABBY_NETWORK_PORT", str(varsayilan_port)))
        except ValueError:
            ag_port = parsed.port or (443 if parsed.scheme == "https" else 3000)
        try:
            baglanti = socket.create_connection((ag_hedef, ag_port), timeout=0.6)
            baglanti.close()
            ag_durumu["bagli"] = True
        except OSError:
            ag_durumu["bagli"] = False
            _ag_yeniden_baglan_tetikle(simdi)
        return bool(ag_durumu["bagli"])

    offline_servisi = OfflineServisi(_ag_bagli_mi)
    offline_servisi.baslat()

    def _okuyucu_hata_metni_uret() -> str:
        giris_yok = GIRIS_USB_PORT not in bagli_portlar
        cikis_yok = CIKIS_USB_PORT not in bagli_portlar
        if giris_yok and cikis_yok:
            return "Giris ve Cikis Kart Okuyucularinda Hata Var"
        if giris_yok:
            return "Giris Kart Okuyucusunda Hata Var"
        if cikis_yok:
            return "Cikis Kart Okuyucusunda Hata Var"
        return ""

    def _hata_metni_uret() -> str:
        okuyucu_hatasi = _okuyucu_hata_metni_uret()
        if okuyucu_hatasi:
            return okuyucu_hatasi
        if not _ag_bagli_mi():
            try:
                import offline_db

                if offline_db.personel_sayisi() > 0:
                    return ""
            except Exception:
                pass
            return "Offline mod - sunucuya erisilemiyor (kisi listesi bos)"
        return ""

    def _kiosk_one_getir() -> None:
        try:
            arayuz_kok.deiconify()
            arayuz_kok.attributes("-topmost", KIOSK_PENCERE_USTTE)
            arayuz_kok.lift()
            arayuz_kok.focus_force()
        except tk.TclError:
            pass

    def _bekleme_video_timer_iptal() -> None:
        nonlocal bekleme_video_after_id
        if bekleme_video_after_id is None:
            return
        try:
            arayuz_kok.after_cancel(bekleme_video_after_id)
        except tk.TclError:
            pass
        bekleme_video_after_id = None

    def _bekleme_video_durdur() -> None:
        _bekleme_video_timer_iptal()
        if bekleme_video.acik_mi() or bekleme_video.calisiyor_mu():
            bekleme_video.durdur()
        _kiosk_one_getir()

    def _bekleme_video_baslat() -> None:
        nonlocal bekleme_video_after_id
        bekleme_video_after_id = None
        if okuma_isleniyor or time.time() < mesaj_gosterime_kadar:
            _bekleme_video_zamanla()
            return
        if _hata_metni_uret() and not _okuyucu_hata_metni_uret():
            _bekleme_video_zamanla()
            return
        try:
            arayuz_kok.attributes("-topmost", False)
        except tk.TclError:
            pass
        url = bekleme_video_url_uret(oku_ayarlar().servis_url)
        LOG.info("Bekleme videosu isteniyor: %s", url)
        if not bekleme_video.baslat(url):
            _kiosk_one_getir()
            _bekleme_video_zamanla()

    def _bekleme_video_zamanla() -> None:
        nonlocal bekleme_video_after_id
        if bekleme_video.acik_mi():
            return
        if bekleme_video_after_id is not None:
            return
        gecikme_s = max(BEKLEME_VIDEO_BASLAMA_SANIYE, 1.0)
        try:
            bekleme_video_after_id = arayuz_kok.after(
                int(gecikme_s * 1000),
                _bekleme_video_baslat,
            )
        except tk.TclError:
            bekleme_video_after_id = None

    def _asamalari_iptal_et() -> None:
        nonlocal asama_after_id, hazir_after_id
        if asama_after_id is not None:
            try:
                arayuz_kok.after_cancel(asama_after_id)
            except tk.TclError:
                pass
            asama_after_id = None
        if hazir_after_id is not None:
            try:
                arayuz_kok.after_cancel(hazir_after_id)
            except tk.TclError:
                pass
            hazir_after_id = None

    def _hazir_ya_da_hata() -> None:
        nonlocal aktif_hata_metni, hazir_after_id
        hazir_after_id = None
        aktif_hata_metni = _hata_metni_uret()
        if aktif_hata_metni:
            uygulama.merkez_hata_goster(aktif_hata_metni)
        else:
            uygulama.hazir_ekrana_gec()
            _bekleme_video_zamanla()

    def okuma_ekrana(oge: dict) -> None:
        nonlocal asama_after_id, hazir_after_id, okuma_isleniyor
        _bekleme_video_durdur()
        if okuma_isleniyor:
            LOG.info("Kart okuma atlandi; onceki okuma isleniyor: %s", oge)
            return

        LOG.info("Kart okundu: %s", oge)
        usb_port = oge.get("usb_port")
        if usb_port not in (GIRIS_USB_PORT, CIKIS_USB_PORT):
            LOG.warning("Kart endpoint'e gonderilmedi; port tanimsiz: %s", oge)
            uygulama.merkez_hata_goster("Kart okuyucu portu taninamadi")
            _bekleme_video_zamanla()
            return

        if usb_port not in bagli_portlar:
            LOG.warning(
                "Kart portu durum listesinde yok ama endpoint'e gonderilecek: %s",
                oge,
            )

        is_giris = usb_port == GIRIS_USB_PORT
        okuma_isleniyor = True
        _asamalari_iptal_et()
        uygulama.islem_bekleniyor_goster(is_giris)
        okuma = dict(oge)

        def _arka_plan() -> None:
            sonuc = kart_okuma_isle(okuma, is_giris, _ag_bagli_mi)

            def _ui_sonuc() -> None:
                nonlocal okuma_isleniyor, mesaj_gosterime_kadar
                ok, msg, yon_giris, ad, saat = sonuc
                if ok:
                    # Sunucu acik metin mesaj dondururse ekranda onu goster.
                    if msg:
                        uygulama.sunucu_mesaji_goster(msg)
                    else:
                        uygulama.islem_basarili_goster(ad, saat, yon_giris)
                else:
                    uygulama.merkez_hata_goster(msg)
                mesaj_gosterime_kadar = time.time() + mesaj_kilit_s
                okuma_isleniyor = False
                _bekleme_video_zamanla()

            try:
                arayuz_kok.after(0, _ui_sonuc)
            except tk.TclError:
                pass

        threading.Thread(target=_arka_plan, name="kart-api", daemon=True).start()

    kuyruk_tuketici(sonuc_kuyrugu, okuma_ekrana, arayuz_kok, 50)

    def durum_guncelle() -> None:
        nonlocal bagli_portlar, aktif_hata_metni
        try:
            liste = okuyucu_aygitlarini_listele()
            uygulama.bagli_okuyuculari_guncelle(liste)
            bagli_portlar = {
                int(g.usb_port)
                for g in liste
                if isinstance(getattr(g, "usb_port", None), int)
            }
            aktif_hata_metni = _hata_metni_uret()
            if okuma_isleniyor or time.time() < mesaj_gosterime_kadar:
                return

            # Chromium dustuyse / beyaz ekranda takildiysa kiosk'u geri getir
            if bekleme_video.dustu_mu():
                LOG.warning("Bekleme videosu dustu; kiosk ekrani geri getiriliyor")
                _bekleme_video_durdur()
                if aktif_hata_metni:
                    uygulama.merkez_hata_goster(aktif_hata_metni)
                else:
                    uygulama.hazir_ekrana_gec()
                    _bekleme_video_zamanla()
                return

            if bekleme_video.acik_mi():
                return
            if aktif_hata_metni:
                uygulama.merkez_hata_goster(aktif_hata_metni)
            else:
                uygulama.hazir_ekrana_gec()
            _bekleme_video_zamanla()
        except Exception:
            LOG.exception("durum yenileme")

    def durum_zamanlamasi() -> None:
        durum_guncelle()
        try:
            arayuz_kok.after(
                int(OKUYUCU_YENIDEN_TARAMA_SANIYE * 1000),
                durum_zamanlamasi,
            )
        except tk.TclError:
            pass

    def usb_aninda_yenile() -> None:
        try:
            izleyici._yeniden_bagla()
        except Exception:
            LOG.exception("usb aninda yeniden bagla")
        try:
            arayuz_kok.after(0, durum_guncelle)
        except tk.TclError:
            pass

    durum_zamanlamasi()
    _bekleme_video_zamanla()

    udev_izleme_baslat(usb_aninda_yenile, udev_dur)

    try:
        izleyici.baslat()
    except Exception:
        LOG.exception("izleyici baslatma")

    def tarama_thread() -> None:
        try:
            izleyici.tarama_dongusu(OKUYUCU_YENIDEN_TARAMA_SANIYE)
        except Exception:
            LOG.exception("tarama thread")

    threading.Thread(target=tarama_thread, name="okuyucu-tarama", daemon=True).start()

    def kapat() -> None:
        udev_dur.set()
        offline_servisi.durdur()
        heartbeat_servisi.durdur()
        _asamalari_iptal_et()
        _bekleme_video_durdur()
        try:
            izleyici.durdur()
        except Exception:
            LOG.exception("izleyici durdurma")
        try:
            arayuz_kok.destroy()
        except tk.TclError:
            pass

    arayuz_kok.protocol("WM_DELETE_WINDOW", kapat)

    try:
        arayuz_kok.mainloop()
    except KeyboardInterrupt:
        kapat()
    finally:
        udev_dur.set()
        heartbeat_servisi.durdur()
        try:
            izleyici.durdur()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger(__name__).exception("kiosk kritik hata")
        sys.exit(1)
