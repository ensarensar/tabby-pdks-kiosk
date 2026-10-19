# -*- coding: utf-8 -*-
"""Arka planda kuyruk flush ve 12 saatte bir personel listesi çekimi."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import personel_sync

LOG = logging.getLogger(__name__)

_KONTROL_S = 10.0
_PERSONEL_ARALIK_S = 12 * 3600


class OfflineServisi:
    def __init__(self, online_mi: Callable[[], bool]) -> None:
        self._online_mi = online_mi
        self._dur = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._once_online = False
        self._son_personel_sync = 0.0

    def baslat(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._dur.clear()
        self._thread = threading.Thread(target=self._dongu, name="tabby-offline", daemon=True)
        self._thread.start()
        LOG.info("Offline servisi baslatildi.")

    def durdur(self) -> None:
        self._dur.set()

    def _kuyruk_gonder(self, neden: str) -> None:
        try:
            import offline_db

            offline_db.meta_yaz("son_kuyruk_flush_neden", neden)
            ok, hata, meta = personel_sync.kuyruk_flush()
            if ok:
                LOG.info(
                    "Kuyruk flush (%s): gonderilen=%s kalan=%s",
                    neden,
                    meta.get("gonderilen"),
                    meta.get("kalan"),
                )
            elif hata:
                LOG.warning("Kuyruk flush basarisiz (%s): %s", neden, hata)
        except Exception:
            LOG.exception("Kuyruk flush hatasi (%s)", neden)

    def _personel_cek(self, neden: str) -> None:
        try:
            ok, hata, meta = personel_sync.personel_senkronize(tam_yenile=True)
            if ok:
                self._son_personel_sync = time.time()
                LOG.info(
                    "Personel listesi cekildi (%s): %s kayit",
                    neden,
                    meta.get("personel_sayisi"),
                )
            else:
                LOG.warning("Personel listesi cekilemedi (%s): %s", neden, hata)
        except Exception:
            LOG.exception("Personel listesi hatasi (%s)", neden)

    def _dongu(self) -> None:
        while not self._dur.is_set():
            online = self._online_mi()
            if online:
                if not self._once_online:
                    LOG.info("Sunucu baglantisi geldi; kuyruk ve kisi listesi senkron")
                    self._kuyruk_gonder("boot")
                    self._personel_cek("boot")
                    self._once_online = True
                else:
                    self._kuyruk_gonder("periyodik")
                    if (time.time() - self._son_personel_sync) >= _PERSONEL_ARALIK_S:
                        self._personel_cek("12saat")
            else:
                if self._once_online:
                    LOG.warning("Sunucu baglantisi kesildi; kartlar yerel kuyruga yazilacak")
                self._once_online = False
            if self._dur.wait(_KONTROL_S):
                break
