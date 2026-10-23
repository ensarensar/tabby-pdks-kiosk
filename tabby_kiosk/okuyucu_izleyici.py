# -*- coding: utf-8 -*-
"""
Her fiziksel input aygiti icin ayri evdev okuma; Enter ile kart tamamlanir.
"""
from __future__ import annotations

import logging
import queue
import select
import threading
import time
from typing import Callable, Dict, List

from config import OKUYUCU_BOS_BEKLEME_MS, OKUYUCU_GRAB_AKTIF, TABBY_DEBUG_TUS
from usb_aygitlari import GirisAygiti, okuyucu_aygitlarini_listele

LOG = logging.getLogger(__name__)

TusHarfCevirici = Dict[str, str]


def _tus_haritasi() -> TusHarfCevirici:
    try:
        import evdev.ecodes as e
    except ImportError:
        return {}

    m: TusHarfCevirici = {}
    for i in range(10):
        m["KEY_%d" % i] = str(i)
        m["KEY_KP%d" % i] = str(i)
    for hx, ch in zip(
        ("A", "B", "C", "D", "E", "F"),
        ("A", "B", "C", "D", "E", "F"),
    ):
        m["KEY_%s" % hx] = ch
    m["KEY_ENTER"] = "\n"
    m["KEY_KPENTER"] = "\n"
    m["KEY_TAB"] = "\n"
    m["KEY_LINEFEED"] = "\n"
    return m


class OkuyucuIzleyici:
    """
    Arka planda aygitlari izler; tamamlanan okumalari kuyruga yazar.
    kuyruk ogesi: dict(okuyucu_adi, okuyucu_kisa, kart_numarasi, zaman)
    """

    def __init__(self, sonuc_kuyrugu: "queue.Queue[dict]") -> None:
        self._sonuc_kuyrugu = sonuc_kuyrugu
        self._dur = threading.Event()
        self._is_parcalari: Dict[str, threading.Thread] = {}
        self._kilidi = threading.Lock()

    def baslat(self) -> None:
        self._dur.clear()
        self._yeniden_bagla()

    def durdur(self) -> None:
        self._dur.set()
        with self._kilidi:
            threads = list(self._is_parcalari.values())
        for t in threads:
            if t.is_alive():
                t.join(timeout=2.5)
        with self._kilidi:
            self._is_parcalari.clear()

    def _thread_sonlandi(self, yol: str) -> None:
        with self._kilidi:
            self._is_parcalari.pop(yol, None)

    def _yeniden_bagla(self) -> None:
        try:
            import evdev  # noqa: F401
        except ImportError:
            LOG.warning("evdev yuklu degil")
            return

        aygitlar: List[GirisAygiti] = okuyucu_aygitlarini_listele()
        harita = _tus_haritasi()
        LOG.debug(
            "Okuyucu tarama: %s aygit bulundu: %s",
            len(aygitlar),
            [
                {
                    "yol": g.yol,
                    "ad": g.ad,
                    "kisa": g.kisa_ad,
                    "usb_port": g.usb_port,
                }
                for g in aygitlar
            ],
        )

        with self._kilidi:
            for g in aygitlar:
                if g.yol in self._is_parcalari:
                    continue
                tr = threading.Thread(
                    target=self._aygit_dongusu,
                    args=(g, harita),
                    name="okuyucu-%s" % g.yol,
                    daemon=True,
                )
                self._is_parcalari[g.yol] = tr
                tr.start()
                LOG.info(
                    "Okuyucu thread baslatildi: yol=%s ad=%s usb_port=%s grab=%s",
                    g.yol,
                    g.ad,
                    g.usb_port,
                    OKUYUCU_GRAB_AKTIF,
                )

    def tarama_dongusu(self, aralik_saniye: float) -> None:
        """Ayri bir thread icinde periyodik yeniden baglanti."""
        while not self._dur.is_set():
            try:
                self._yeniden_bagla()
            except Exception:
                LOG.exception("okuyucu tarama hatasi")
            if self._dur.wait(timeout=max(aralik_saniye, 0.5)):
                break

    def _aygit_dongusu(self, aygit: GirisAygiti, harita: TusHarfCevirici) -> None:
        try:
            import evdev
            from evdev import categorize, ecodes
        except ImportError:
            self._thread_sonlandi(aygit.yol)
            return

        yol = aygit.yol
        buffer = ""
        son_rakam_zaman = 0.0
        bos_bekleme_s = max(OKUYUCU_BOS_BEKLEME_MS, 50) / 1000.0

        def tamamla_okuma() -> None:
            nonlocal buffer, son_rakam_zaman
            parca = buffer.strip()
            buffer = ""
            son_rakam_zaman = 0.0
            if parca:
                LOG.info(
                    "Kart okuma tamamlandi: okuyucu=%s usb_port=%s kart=%s",
                    aygit.kisa_ad,
                    aygit.usb_port,
                    parca,
                )
                self._sonuc_kuyrugu.put(
                    {
                        "okuyucu_adi": aygit.ad,
                        "okuyucu_kisa": aygit.kisa_ad,
                        "usb_port": aygit.usb_port,
                        "kart_numarasi": parca,
                        "zaman": time.time(),
                    }
                )

        try:
            dev = evdev.InputDevice(yol)
        except OSError as e:
            LOG.warning("Aygit acilamadi %s: %s", yol, e)
            self._thread_sonlandi(yol)
            return

        if OKUYUCU_GRAB_AKTIF:
            try:
                dev.grab()
                LOG.info("Okuyucu grab aktif: %s", yol)
            except OSError as e:
                LOG.warning("Okuyucu grab basarisiz %s: %s", yol, e)

        try:
            fd = dev.fd
            poll_s = min(0.05, max(0.02, bos_bekleme_s / 5.0))
            LOG.info(
                "Okuyucu olay dongusu basladi: yol=%s ad=%s usb_port=%s",
                yol,
                aygit.ad,
                aygit.usb_port,
            )
            while not self._dur.is_set():
                r, _, _ = select.select([fd], [], [], poll_s)
                now = time.time()
                if (
                    buffer
                    and son_rakam_zaman > 0
                    and (now - son_rakam_zaman) >= bos_bekleme_s
                ):
                    tamamla_okuma()
                if not r:
                    continue
                try:
                    for event in dev.read():
                        if self._dur.is_set():
                            break
                        if event.type != ecodes.EV_KEY:
                            continue
                        kev = categorize(event)
                        if kev.keystate != kev.key_down:
                            continue
                        kod = kev.keycode
                        if isinstance(kod, list):
                            kod = kod[0] if kod else ""
                        kod_str = str(kod)
                        if TABBY_DEBUG_TUS:
                            LOG.info(
                                "tus %s yol=%s buffer_len=%s",
                                kod_str,
                                yol,
                                len(buffer),
                            )
                        ch = harita.get(kod_str, "")
                        if ch == "\n":
                            tamamla_okuma()
                        elif ch:
                            buffer += ch
                            son_rakam_zaman = time.time()
                except OSError:
                    LOG.info("Aygit kesildi %s", yol)
                    break
                except BlockingIOError:
                    continue
        except Exception:
            LOG.exception("Aygit dongusu hata %s", yol)
        finally:
            try:
                if OKUYUCU_GRAB_AKTIF:
                    dev.ungrab()
            except OSError:
                pass
            try:
                dev.close()
            except OSError:
                pass
            self._thread_sonlandi(yol)


def kuyruk_tuketici(
    kuyruk: "queue.Queue[dict]",
    isleyici: Callable[[dict], None],
    kok: object,
    aralik_ms: int = 50,
) -> None:
    """Tkinter ana thread icinde after ile kuyruk bosalt."""

    def bir_tur() -> None:
        try:
            while True:
                oge = kuyruk.get_nowait()
                try:
                    isleyici(oge)
                except Exception:
                    LOG.exception("okuma isleyici hatasi")
        except queue.Empty:
            pass
        try:
            kok.after(aralik_ms, bir_tur)
        except Exception:
            pass

    bir_tur()
