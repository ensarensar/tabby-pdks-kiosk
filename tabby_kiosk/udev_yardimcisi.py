# -*- coding: utf-8 -*-
"""
Linux udev: input alt sistemi degisince okuyucu listesini hemen yenilemeyi tetikler.
pyudev yoksa veya hata olursa sessizce cikilir; periyodik tarama yine calisir.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

LOG = logging.getLogger(__name__)


def udev_izleme_baslat(
    yenile: Callable[[], None],
    dur_event: threading.Event,
) -> Optional[threading.Thread]:
    """
    yenile: thread-safe olarak cagrilabilir hafif fonksiyon (or. Tk after ile UI).
    dur_event: set olunca dongu biter.
    """
    try:
        import pyudev  # type: ignore
    except ImportError:
        LOG.info("pyudev yok; sadece zamanli USB tarama kullanilacak")
        return None

    def dongu() -> None:
        try:
            baglam = pyudev.Context()
            mon = pyudev.Monitor.from_netlink(baglam)
            mon.filter_by(subsystem="input")
        except Exception:
            LOG.exception("udev monitör baslatilamadi")
            return

        while not dur_event.is_set():
            try:
                cihaz = mon.poll(timeout=2.0)
            except Exception:
                LOG.exception("udev poll")
                continue
            if cihaz is None:
                continue
            try:
                yenile()
            except Exception:
                LOG.exception("udev yenile callback")

    tr = threading.Thread(target=dongu, name="tabby-udev", daemon=True)
    tr.start()
    return tr
