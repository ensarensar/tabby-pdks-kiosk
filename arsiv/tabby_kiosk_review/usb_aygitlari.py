# -*- coding: utf-8 -*-
"""
Linux /dev/input altinda USB klavye benzeri aygitlari listeler.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from config import (
    CIKIS_USB_PORT,
    GIRIS_USB_PORT,
    HARIC_OKUYUCU_ISIM_PARCALARI,
    SADECE_ISIM_ICERIR,
)

LOG = logging.getLogger(__name__)


@dataclass
class GirisAygiti:
    """Tek bir okunabilir input event aygiti."""

    yol: str
    ad: str
    kisa_ad: str
    usb_port: Optional[int] = None


def _linux_mu() -> bool:
    return os.name == "posix" and os.path.isdir("/dev/input")


def _event_yollari() -> List[str]:
    if not _linux_mu():
        return []
    try:
        isimler = sorted(
            f for f in os.listdir("/dev/input") if f.startswith("event")
        )
    except OSError as e:
        LOG.warning("event listesi alinamadi: %s", e)
        return []
    return [os.path.join("/dev/input", n) for n in isimler]


def _isim_haric_mi(ad: str) -> bool:
    a = ad.lower()
    return any(p in a for p in HARIC_OKUYUCU_ISIM_PARCALARI)


def _isim_sadece_mi(ad: str) -> bool:
    if not SADECE_ISIM_ICERIR:
        return True
    a = ad.lower()
    return any(s in a for s in SADECE_ISIM_ICERIR)


def okuyucu_aygitlarini_listele() -> List[GirisAygiti]:
    """
    evdev ile EV_KEY destekleyen ve rakam/enter gonderebilen aygitlari dondurur.
    evdev yoksa veya hata olursa bos liste.
    """
    sonuc: List[GirisAygiti] = []
    if not _linux_mu():
        return sonuc

    try:
        import evdev
    except ImportError:
        LOG.debug("evdev modulu yok")
        return sonuc

    for yol in _event_yollari():
        try:
            dev = evdev.InputDevice(yol)
        except OSError as e:
            LOG.debug("%s acilamadi: %s", yol, e)
            continue
        try:
            cap = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
        except OSError:
            dev.close()
            continue

        if not cap:
            dev.close()
            continue

        cap_set = set(cap)
        # Tam rakam satiri veya tam numpad (Enter yetenek listesinde olmayabilir)
        std_rakam = {getattr(evdev.ecodes, "KEY_%d" % i) for i in range(10)}
        kp_rakam = {getattr(evdev.ecodes, "KEY_KP%d" % i) for i in range(10)}
        if not (std_rakam.issubset(cap_set) or kp_rakam.issubset(cap_set)):
            dev.close()
            continue

        ad = (dev.name or "").strip() or yol
        dev.close()

        if _isim_haric_mi(ad):
            continue
        if not _isim_sadece_mi(ad):
            continue

        kisa = _kisa_etiket(yol, ad)
        usb_port = _usb_portunu_bul(yol)
        if usb_port is None:
            LOG.debug("USB port tespit edilemedi: %s (%s)", yol, ad)
        sonuc.append(
            GirisAygiti(yol=yol, ad=ad, kisa_ad=kisa, usb_port=usb_port)
        )

    return sonuc


def _kisa_etiket(yol: str, ad: str) -> str:
    """USB Reader 1, USB Reader 2 ... benzeri kisa etiket."""
    m = re.search(r"event(\d+)$", yol)
    idx = int(m.group(1)) if m else 0
    return "USB Reader %s" % (idx + 1)


def _usb_portunu_bul(yol: str) -> Optional[int]:
    """
    /dev/input/eventX yolundan USB port numarasini cikarmaya calisir.
    Ornek sysfs parcalari:
      .../usb1/1-1.3/1-1.3:1.0/... -> port 3
      .../usb1/1-1/1-1:1.0/...     -> port 1
    """
    event_adi = os.path.basename(yol)
    if not event_adi:
        return None

    # En guvenilir kaynaklardan biri: /dev/input/by-path symlink adlari.
    by_path_port = _by_path_uzerinden_port_bul(event_adi)
    if by_path_port is not None:
        return by_path_port

    sysfs_yol = os.path.join("/sys/class/input", event_adi, "device")
    try:
        gercek = os.path.realpath(sysfs_yol)
    except OSError:
        return None

    adaylar = _port_adaylarini_topla(gercek)
    son_adaylar = _port_son_adaylarini_topla(gercek)

    # Bazi sistemlerde en guvenilir bilgi device/phys dosyasinda olur.
    phys_yol = os.path.join(sysfs_yol, "phys")
    try:
        with open(phys_yol, "r", encoding="utf-8", errors="ignore") as f:
            phys = f.read().strip()
            adaylar.update(_port_adaylarini_topla(phys))
            son_adaylar.update(_port_son_adaylarini_topla(phys))
    except OSError:
        pass

    if not adaylar and not son_adaylar:
        return None

    # Once zincirin son segmentinden gelen adaylara bak.
    for hedef in (GIRIS_USB_PORT, CIKIS_USB_PORT):
        if hedef in son_adaylar:
            return hedef

    # Son segmentte yoksa, genel adaylara bak.
    for hedef in (GIRIS_USB_PORT, CIKIS_USB_PORT):
        if hedef in adaylar:
            return hedef

    # Aksi halde son segment adaylarindan, o da yoksa tum adaylardan en buyugunu sec.
    if son_adaylar:
        return sorted(son_adaylar)[-1]
    return sorted(adaylar)[-1]


def _by_path_uzerinden_port_bul(event_adi: str) -> Optional[int]:
    """
    /dev/input/by-path altindaki symlink adindan USB portu yakalamaya calisir.
    Ornek:
      pci-...-usb-0:1.3:1.0-event-kbd -> 3
      platform-...-usb-0:1:1.0-event-kbd -> 1
    """
    kok = "/dev/input/by-path"
    if not os.path.isdir(kok):
        return None

    try:
        adaylar = sorted(os.listdir(kok))
    except OSError:
        return None

    for isim in adaylar:
        if not isim.endswith("-event-kbd"):
            continue
        link = os.path.join(kok, isim)
        try:
            hedef = os.path.realpath(link)
        except OSError:
            continue
        if os.path.basename(hedef) != event_adi:
            continue

        # usb-0:1.3:1.0 veya usb-0:1:1.0 gibi desenler
        m = re.search(r"usb-[^:]*:(\d+(?:\.\d+)*):\d+\.\d+", isim)
        if not m:
            m = re.search(r"usb-[^-]*-(\d+(?:\.\d+)*)", isim)
        if not m:
            continue
        zincir = m.group(1).strip()
        son = zincir.split(".")[-1] if zincir else ""
        if son.isdigit():
            return int(son)
    return None


def _port_adaylarini_topla(metin: str) -> set[int]:
    adaylar: set[int] = set()
    if not metin:
        return adaylar

    # Ornek: .../1-1.3/1-1.3:1.0/... -> 1,3
    for m in re.finditer(r"\b\d+-((?:\d+\.)*\d+)(?::|\b)", metin):
        for parca in m.group(1).split("."):
            if parca.isdigit():
                adaylar.add(int(parca))

    # Ornek phys: usb-3f980000.usb-1.3/input0 -> 1,3
    for m in re.finditer(r"usb-[^/]*-(\d+(?:\.\d+)*)(?:/|$)", metin):
        for parca in m.group(1).split("."):
            if parca.isdigit():
                adaylar.add(int(parca))

    return adaylar


def _port_son_adaylarini_topla(metin: str) -> set[int]:
    """
    USB zincirinin yalnizca son segmentini aday olarak alir.
    .../1-1.3/... icin 3, .../1-1/... icin 1.
    """
    adaylar: set[int] = set()
    if not metin:
        return adaylar

    for m in re.finditer(r"\b\d+-((?:\d+\.)*\d+)(?::|\b)", metin):
        zincir = m.group(1).strip()
        son = zincir.split(".")[-1] if zincir else ""
        if son.isdigit():
            adaylar.add(int(son))

    for m in re.finditer(r"usb-[^/]*-(\d+(?:\.\d+)*)(?:/|$)", metin):
        zincir = m.group(1).strip()
        son = zincir.split(".")[-1] if zincir else ""
        if son.isdigit():
            adaylar.add(int(son))

    return adaylar


def aygit_yolundan_etiket(yol: str, varsayilan_ad: str) -> str:
    """Bilinen yol icin kisa etiket."""
    if varsayilan_ad and varsayilan_ad.strip():
        return varsayilan_ad.strip()
    return _kisa_etiket(yol, yol)
