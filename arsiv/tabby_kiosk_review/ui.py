# -*- coding: utf-8 -*-
"""
Tkinter tam ekran kiosk: beyaz tasarim, sol ust tabby, merkez mesaj + tarih/saat,
alt GIRIS / CIKIS panelleri.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
import tkinter as tk
from tkinter import font as tkfont
from typing import Any, Iterable, List, Optional

from config import (
    BOOTSTRAP_DANGER,
    BOOTSTRAP_PRIMARY,
    CIKIS_USB_PORT,
    FONT_AILE,
    FONT_ALT_KART,
    FONT_ANA_BUYUK,
    FONT_DURUM,
    FONT_GUN,
    FONT_KART,
    FONT_MARKA,
    FONT_ORTA_OKUYUCU,
    FONT_SAAT,
    FONT_TARIH,
    GELISTIRME_ESCAPE_CIKIS,
    GIRIS_USB_PORT,
    KIOSK_ALT_GRADYAN_H,
    KIOSK_ALT_PADX,
    KIOSK_ALT_PADY,
    KIOSK_BASLIK_PADY1,
    KIOSK_BASLIK_PADY2,
    KIOSK_DIS_PADX,
    KIOSK_DIS_PADY,
    KIOSK_FONT_CARPAN,
    KIOSK_IMLEC_GIZLE,
    KIOSK_PANEL_CANVAS_H,
    KIOSK_PANEL_GAP,
    KIOSK_PENCERE_USTTE,
    KIOSK_REF_GENISLIK,
    KIOSK_REF_YUKSEKLIK,
    KIOSK_UST_PADY_ALT,
    LOGO_PANEL_MAX_H,
    LOGO_PANEL_MAX_W,
    LOGO_TABBY_MAX_H,
    LOGO_TABBY_MAX_W,
    METIN_ANA_SATIR1,
    METIN_ANA_SATIR2,
    METIN_BEKLEYINIZ,
    METIN_CIKIS,
    METIN_GIRIS,
    METIN_HAZIR,
    METIN_KART_ETIKET,
    METIN_OKUYUCU_ETIKET,
    METIN_SON_OKUMA,
    RENK_ARKA,
    RENK_ARKA_UST,
    RENK_BEYAZ,
    RENK_CIKIS_KIRMIZI,
    RENK_GIRIS_YESIL,
    RENK_METIN_KOYU,
    RENK_UYARI,
    RENK_VURGULU,
    RESIM_CIKIS_LOGO,
    RESIM_GIRIS_LOGO,
    RESIM_TABBY_LOGO,
    SON_OKUMA_GOSTERIM_SANIYE,
    TAM_EKRAN,
    TURKCE_GUNLER,
)
from device_info import oku_ekran_bilgisi

LOG = logging.getLogger(__name__)


class KioskArayuz:
    def __init__(self, kok: tk.Tk) -> None:
        self._resim_tutucular: List[Any] = []
        self.kok = kok
        self.kok.title("Tabby Kiosk")
        self.kok.configure(bg=RENK_ARKA)

        if TAM_EKRAN:
            self.kok.attributes("-fullscreen", True)
        self.kok.attributes("-topmost", KIOSK_PENCERE_USTTE)

        self.kok.bind("<Configure>", self._boyut_degisti)
        self._son_genislik = 0
        self._son_yukseklik = 0
        self._son_okuma_after_id: Optional[Any] = None
        self._saat_zamanlayici: Optional[str] = None
        self._alt_bilgi_after_id: Optional[Any] = None

        if GELISTIRME_ESCAPE_CIKIS:
            self.kok.bind("<Escape>", lambda e: self.kok.quit())

        ana = tk.Frame(self.kok, bg=RENK_ARKA)
        ana.pack(
            fill=tk.BOTH,
            expand=True,
            padx=KIOSK_DIS_PADX,
            pady=(KIOSK_DIS_PADY, 0),
        )
        self._ana = ana
        self._alt_bolum_bg = RENK_ARKA

        self.durum_strip = tk.Frame(ana, bg=self._alt_bolum_bg)
        self.durum_strip.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 0))

        alt_iki = tk.Frame(ana, bg=self._alt_bolum_bg)
        alt_iki.pack(
            side=tk.BOTTOM,
            fill=tk.X,
            pady=(0, 0),
        )
        alt_iki._sabit_arka_plan = True  # type: ignore[attr-defined]
        alt_iki.columnconfigure(0, weight=1)
        alt_iki.columnconfigure(1, weight=0)
        alt_iki.columnconfigure(2, weight=1)
        _yarim_gap = max(2, KIOSK_PANEL_GAP // 2)

        self._alt_gradyan = tk.Canvas(
            ana,
            height=KIOSK_ALT_GRADYAN_H,
            bg=RENK_ARKA,
            highlightthickness=0,
            bd=0,
        )
        self._alt_gradyan.pack(side=tk.BOTTOM, fill=tk.X)
        self._alt_gradyan.bind("<Configure>", self._alt_gradyan_ciz)

        sol_panel = tk.Frame(alt_iki, bg=self._alt_bolum_bg)
        sol_panel.grid(row=0, column=0, sticky="nsew", padx=(0, _yarim_gap))
        sol_panel._sabit_arka_plan = True  # type: ignore[attr-defined]
        orta_panel = tk.Frame(alt_iki, bg=self._alt_bolum_bg)
        orta_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 4))
        orta_panel._sabit_arka_plan = True  # type: ignore[attr-defined]
        sag_panel = tk.Frame(alt_iki, bg=self._alt_bolum_bg)
        sag_panel.grid(row=0, column=2, sticky="nsew", padx=(_yarim_gap, 0))
        sag_panel._sabit_arka_plan = True  # type: ignore[attr-defined]

        self._son_alt_bilgi_metin = self._cihaz_bilgi_metni()
        self._alt_bilgi_etiket = tk.Label(
            orta_panel,
            text=self._son_alt_bilgi_metin,
            bg=self._alt_bolum_bg,
            fg=RENK_METIN_KOYU,
            justify=tk.CENTER,
            anchor=tk.CENTER,
            font=(FONT_AILE, max(7, FONT_DURUM)),
        )
        self._alt_bilgi_etiket.pack(fill=tk.BOTH, expand=True, padx=(2, 2), pady=(2, 2))

        img_giris = self._resim_yukle(
            RESIM_GIRIS_LOGO, LOGO_PANEL_MAX_W, LOGO_PANEL_MAX_H
        )
        img_cikis = self._resim_yukle(
            RESIM_CIKIS_LOGO, LOGO_PANEL_MAX_W, LOGO_PANEL_MAX_H
        )
        if img_giris:
            tk.Label(
                sol_panel,
                image=img_giris,
                bg=self._alt_bolum_bg,
                anchor=tk.W,
                justify=tk.LEFT,
            ).pack(fill=tk.BOTH, expand=True)
        else:
            self._panel_resim_yedek(sol_panel, True)
        if img_cikis:
            tk.Label(
                sag_panel,
                image=img_cikis,
                bg=self._alt_bolum_bg,
                anchor=tk.E,
                justify=tk.RIGHT,
            ).pack(fill=tk.BOTH, expand=True)
        else:
            self._panel_resim_yedek(sag_panel, False)

        ust = tk.Frame(ana, bg=RENK_ARKA)
        ust.pack(
            side=tk.TOP,
            fill=tk.X,
            anchor=tk.NW,
            pady=(0, KIOSK_UST_PADY_ALT),
        )

        merkez = tk.Frame(ana, bg=RENK_ARKA)
        merkez.pack(fill=tk.BOTH, expand=True)

        img_tabby = self._resim_yukle(
            RESIM_TABBY_LOGO, LOGO_TABBY_MAX_W, LOGO_TABBY_MAX_H
        )
        if img_tabby:
            tk.Label(ust, image=img_tabby, bg=RENK_ARKA).pack(anchor=tk.W)
        else:
            self._tabby_metin_yedek(ust)

        self._baslik_font = tkfont.Font(
            family=FONT_AILE, size=FONT_ANA_BUYUK, weight="bold"
        )
        self._tarih_font = tkfont.Font(family=FONT_AILE, size=FONT_TARIH)
        self._gun_font = tkfont.Font(family=FONT_AILE, size=FONT_GUN)
        self._saat_font = tkfont.Font(family=FONT_AILE, size=FONT_SAAT, weight="bold")
        self._orta_okuyucu_font = tkfont.Font(
            family=FONT_AILE, size=FONT_ORTA_OKUYUCU, weight="bold"
        )
        self._kart_font = tkfont.Font(family=FONT_AILE, size=FONT_KART, weight="bold")
        self._alt_kart_font = tkfont.Font(
            family=FONT_AILE, size=FONT_ALT_KART, weight="bold"
        )
        self._durum_font = tkfont.Font(family=FONT_AILE, size=FONT_DURUM)
        self._alt_bilgi_font = tkfont.Font(
            family=FONT_AILE, size=max(7, FONT_DURUM), weight="normal"
        )
        self._alt_bilgi_etiket.configure(font=self._alt_bilgi_font)

        self.baslik_etiket = tk.Label(
            merkez,
            text=METIN_HAZIR,
            bg=RENK_ARKA,
            fg=RENK_METIN_KOYU,
            font=self._baslik_font,
            justify=tk.CENTER,
            anchor=tk.CENTER,
        )
        self.baslik_etiket.pack(
            fill=tk.X,
            padx=(2, 2),
            pady=(KIOSK_BASLIK_PADY1, KIOSK_BASLIK_PADY2),
        )

        self.tarih_saat_kutu = tk.Frame(merkez, bg=RENK_ARKA)
        self.tarih_saat_kutu.pack(fill=tk.X)
        self.tarih_etiket = tk.Label(
            self.tarih_saat_kutu,
            text="",
            bg=RENK_ARKA,
            fg=RENK_METIN_KOYU,
            font=self._tarih_font,
            justify=tk.CENTER,
            anchor=tk.CENTER,
        )
        self.tarih_etiket.pack(fill=tk.X)
        self.gun_etiket = tk.Label(
            self.tarih_saat_kutu,
            text="",
            bg=RENK_ARKA,
            fg=RENK_METIN_KOYU,
            font=self._gun_font,
            justify=tk.CENTER,
            anchor=tk.CENTER,
        )
        self.gun_etiket.pack(fill=tk.X, pady=(2, 2))
        self.saat_etiket = tk.Label(
            self.tarih_saat_kutu,
            text="",
            bg=RENK_ARKA,
            fg=RENK_METIN_KOYU,
            font=self._saat_font,
            justify=tk.CENTER,
            anchor=tk.CENTER,
        )
        self.saat_etiket.pack(fill=tk.X)

        self.orta_okuyucu_etiket = tk.Label(
            merkez,
            text="",
            bg=RENK_ARKA,
            fg=BOOTSTRAP_PRIMARY,
            font=self._orta_okuyucu_font,
            justify=tk.CENTER,
            anchor=tk.CENTER,
        )
        self.kart_etiket = tk.Label(
            merkez,
            text="",
            bg=RENK_ARKA,
            fg=BOOTSTRAP_PRIMARY,
            font=self._kart_font,
            justify=tk.CENTER,
            anchor=tk.CENTER,
        )

        self.bagli_etiket = tk.Frame(self.durum_strip, bg=self._alt_bolum_bg)
        self.bagli_etiket.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 0))
        self._usb_durum_gostergesi_olustur()

        self.son_okuyucu_etiket = tk.Label(
            self.durum_strip,
            text="",
            bg=self._alt_bolum_bg,
            fg=RENK_METIN_KOYU,
            font=self._durum_font,
            anchor=tk.W,
            justify=tk.LEFT,
        )

        self.son_kart_etiket = tk.Label(
            self.durum_strip,
            text="",
            bg=self._alt_bolum_bg,
            fg=RENK_METIN_KOYU,
            font=self._alt_kart_font,
            anchor=tk.W,
            justify=tk.LEFT,
        )

        if KIOSK_IMLEC_GIZLE:
            self._imlec_gizle(self.kok)

        self._alt_bilgi_yenile_dongusu()
        self._saat_dongusu()
        self.hazir_ekrana_gec()

    def _resim_yukle(
        self, yol: str, max_w: int, max_h: int
    ) -> Optional[tk.PhotoImage]:
        if not os.path.isfile(yol):
            LOG.warning("Resim bulunamadi: %s", yol)
            return None
        try:
            from PIL import Image, ImageTk

            im = Image.open(yol)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS  # type: ignore[attr-defined]
            im.thumbnail((max_w, max_h), resample)
            photo = ImageTk.PhotoImage(im)
            self._resim_tutucular.append(photo)
            return photo
        except ImportError:
            LOG.debug("Pillow yok, Tk PhotoImage deneniyor")
        except Exception as e:
            LOG.warning("Pillow ile acilamadi %s: %s", yol, e)
        try:
            img = tk.PhotoImage(file=yol)
            ow = img.width()
            oh = img.height()
            if ow > max_w or oh > max_h:
                fx = max(1, (ow + max_w - 1) // max_w)
                fy = max(1, (oh + max_h - 1) // max_h)
                f = max(fx, fy)
                img = img.subsample(f, f)
            self._resim_tutucular.append(img)
            return img
        except tk.TclError as e:
            LOG.warning("Tk resim: %s", e)
            return None

    def _tabby_metin_yedek(self, ust: tk.Frame) -> None:
        self._marka_font = tkfont.Font(
            family=FONT_AILE, size=FONT_MARKA, weight="normal"
        )
        kutu = tk.Frame(ust, bg=RENK_ARKA)
        kutu.pack(anchor=tk.W)
        tk.Label(
            kutu, text="tab", font=self._marka_font, fg=BOOTSTRAP_PRIMARY, bg=RENK_ARKA
        ).pack(side=tk.LEFT)
        tk.Label(
            kutu, text="b", font=self._marka_font, fg=BOOTSTRAP_DANGER, bg=RENK_ARKA
        ).pack(side=tk.LEFT)
        tk.Label(
            kutu, text="y", font=self._marka_font, fg=BOOTSTRAP_PRIMARY, bg=RENK_ARKA
        ).pack(side=tk.LEFT)

    def _panel_resim_yedek(self, panel: tk.Frame, sola: bool) -> None:
        renk = self._alt_bolum_bg
        cv = tk.Canvas(
            panel,
            height=KIOSK_PANEL_CANVAS_H,
            bg=renk,
            highlightthickness=1,
            highlightbackground=RENK_ARKA,
        )
        cv.pack(fill=tk.BOTH, expand=True)
        cv.bind(
            "<Configure>",
            lambda e, c=cv, s=sola: KioskArayuz._ikon_ciz_yedek(c, s),
        )

    @staticmethod
    def _hex_renk_coz(hex_renk: str) -> tuple[int, int, int]:
        renk = (hex_renk or "").strip().lstrip("#")
        if len(renk) != 6:
            return (11, 31, 58)
        try:
            return (int(renk[0:2], 16), int(renk[2:4], 16), int(renk[4:6], 16))
        except ValueError:
            return (11, 31, 58)

    @staticmethod
    def _hex_renk_yap(r: int, g: int, b: int) -> str:
        rr = max(0, min(255, int(r)))
        gg = max(0, min(255, int(g)))
        bb = max(0, min(255, int(b)))
        return "#%02x%02x%02x" % (rr, gg, bb)

    def _alt_gradyan_ciz(self, _evt=None) -> None:
        try:
            w = max(self._alt_gradyan.winfo_width(), 1)
            h = max(self._alt_gradyan.winfo_height(), 1)
            ust = self._hex_renk_coz(RENK_ARKA)
            parlama = self._hex_renk_coz(RENK_BEYAZ)
            self._alt_gradyan.delete("all")
            for y in range(h):
                uzaklik = abs((y / max(h - 1, 1)) - 0.5) * 2
                oran = max(0.0, 1.0 - uzaklik)
                r = ust[0] + (parlama[0] - ust[0]) * oran
                g = ust[1] + (parlama[1] - ust[1]) * oran
                b = ust[2] + (parlama[2] - ust[2]) * oran
                self._alt_gradyan.create_line(
                    0, y, w, y, fill=self._hex_renk_yap(r, g, b)
                )
        except tk.TclError:
            pass

    def _gradyan_renk(self, y: int, toplam_h: int) -> str:
        return RENK_ARKA_UST

    def _gradyan_uygula(self) -> None:
        return

    @staticmethod
    def _ikon_ciz_yedek(cv: tk.Canvas, sola_ok: bool) -> None:
        try:
            cv.update_idletasks()
            w = max(cv.winfo_width(), 80)
            h = max(cv.winfo_height(), 80)
            cv.delete("all")
            renk = RENK_ARKA
            cv.create_rectangle(0, 0, w, h, outline="", fill=renk)
            mx = max(2, int(h * 0.03))
            y_ok = h * 0.18
            ok_uz = w * 0.2
            if sola_ok:
                cv.create_polygon(
                    mx,
                    y_ok,
                    mx + ok_uz,
                    y_ok - h * 0.07,
                    mx + ok_uz,
                    y_ok + h * 0.07,
                    fill=RENK_METIN_KOYU,
                    outline="",
                )
                cv.create_line(
                    mx + ok_uz, y_ok, w - mx, y_ok, fill=RENK_METIN_KOYU, width=mx
                )
            else:
                cv.create_line(
                    mx, y_ok, w - mx - ok_uz, y_ok, fill=RENK_METIN_KOYU, width=mx
                )
                cv.create_polygon(
                    w - mx,
                    y_ok,
                    w - mx - ok_uz,
                    y_ok - h * 0.07,
                    w - mx - ok_uz,
                    y_ok + h * 0.07,
                    fill=RENK_METIN_KOYU,
                    outline="",
                )
        except tk.TclError:
            pass

    def _saat_dongusu(self) -> None:
        try:
            simdi = datetime.now()
            self.tarih_etiket.configure(text=simdi.strftime("%d.%m.%Y"))
            self.gun_etiket.configure(text=TURKCE_GUNLER[simdi.weekday()])
            self.saat_etiket.configure(text=simdi.strftime("%H:%M"))
        except tk.TclError:
            return
        self._saat_zamanlayici = self.kok.after(1000, self._saat_dongusu)

    def _cihaz_bilgi_metni(self) -> str:
        b = oku_ekran_bilgisi()
        return "cihaz: %s\nag: %s\nip: %s\nmac: %s" % (
            b["cihaz_adi"],
            b["baglanti_metin"],
            b["ip"],
            b["mac"],
        )

    def _alt_bilgi_yenile_dongusu(self) -> None:
        try:
            yeni = self._cihaz_bilgi_metni()
            if yeni != self._son_alt_bilgi_metin:
                self._son_alt_bilgi_metin = yeni
                self._alt_bilgi_etiket.configure(text=yeni)
        except tk.TclError:
            return
        self._alt_bilgi_after_id = self.kok.after(3000, self._alt_bilgi_yenile_dongusu)

    @staticmethod
    def _imlec_gizle(widget: tk.Misc) -> None:
        try:
            widget.configure(cursor="none")
        except tk.TclError:
            pass
        try:
            for c in widget.winfo_children():
                KioskArayuz._imlec_gizle(c)
        except tk.TclError:
            pass

    def _iptal_son_okuma_zamanlayici(self) -> None:
        if self._son_okuma_after_id is not None:
            try:
                self.kok.after_cancel(self._son_okuma_after_id)
            except tk.TclError:
                pass
            self._son_okuma_after_id = None

    def _boyut_degisti(self, _evt=None) -> None:
        w = self.kok.winfo_width()
        h = self.kok.winfo_height()
        if w == self._son_genislik and h == self._son_yukseklik:
            return
        self._son_genislik = w
        self._son_yukseklik = h
        if w < 120:
            return
        try:
            oran_w = max(w / KIOSK_REF_GENISLIK, 0.42)
            oran_h = max(h / KIOSK_REF_YUKSEKLIK, 0.42)
            oran = min(oran_w, oran_h) * KIOSK_FONT_CARPAN
            if hasattr(self, "_marka_font"):
                self._marka_font.configure(
                    size=max(10, int(FONT_MARKA * min(oran, 1.05)))
                )
            self._baslik_font.configure(
                size=max(14, int(FONT_ANA_BUYUK * min(oran, 1.15)))
            )
            self._tarih_font.configure(size=max(11, int(FONT_TARIH * oran)))
            self._gun_font.configure(size=max(11, int(FONT_GUN * oran)))
            self._saat_font.configure(
                size=max(22, int(FONT_SAAT * min(oran, 1.2)))
            )
            self._orta_okuyucu_font.configure(
                size=max(12, int(FONT_ORTA_OKUYUCU * min(oran, 1.12)))
            )
            self._kart_font.configure(
                size=max(16, int(FONT_KART * min(oran, 1.18)))
            )
            self._alt_kart_font.configure(
                size=max(10, int(FONT_ALT_KART * min(oran, 1.05)))
            )
            self._durum_font.configure(size=max(8, int(FONT_DURUM * oran)))
            self._alt_bilgi_font.configure(size=max(7, int(FONT_DURUM * min(oran, 0.95))))
            metin_w = max(120, int(w * 0.98) - (KIOSK_DIS_PADX * 2))
            self.baslik_etiket.configure(wraplength=metin_w)
            self.tarih_etiket.configure(wraplength=metin_w)
            self.gun_etiket.configure(wraplength=metin_w)
            self.saat_etiket.configure(wraplength=metin_w)
            self.orta_okuyucu_etiket.configure(wraplength=metin_w)
            self.kart_etiket.configure(wraplength=metin_w)
        except tk.TclError:
            pass

    def _usb_durum_gostergesi_olustur(self) -> None:
        self._usb_port_noktalari: dict[int, tk.Canvas] = {}
        port_etiketleri = {GIRIS_USB_PORT: "GKO", CIKIS_USB_PORT: "CKO"}
        for port in (GIRIS_USB_PORT, CIKIS_USB_PORT):
            item = tk.Frame(self.bagli_etiket, bg=self._alt_bolum_bg)
            item.pack(side=tk.LEFT, padx=(0, 14))
            nokta = tk.Canvas(
                item,
                width=14,
                height=14,
                bg=self._alt_bolum_bg,
                highlightthickness=0,
                bd=0,
            )
            nokta.pack(side=tk.LEFT)
            tk.Label(
                item,
                text=port_etiketleri.get(port, "USB %s" % port),
                bg=self._alt_bolum_bg,
                fg=RENK_METIN_KOYU,
                font=self._durum_font,
            ).pack(side=tk.LEFT, padx=(6, 0))
            self._usb_port_noktalari[port] = nokta

        self._usb_port_gostergesini_guncelle(set())

    @staticmethod
    def _metinden_port_bul(metin: str) -> Optional[int]:
        if not metin:
            return None
        m = re.search(r"\b(?:usb|port)\s*([0-9]+)\b", metin, flags=re.IGNORECASE)
        if not m:
            return None
        return int(m.group(1))

    def _usb_port_gostergesini_guncelle(self, bagli_portlar: set[int]) -> None:
        for port, nokta in self._usb_port_noktalari.items():
            renk = RENK_METIN_KOYU if port in bagli_portlar else RENK_ARKA
            try:
                nokta.delete("all")
                nokta.create_oval(2, 2, 12, 12, fill=renk, outline=RENK_METIN_KOYU)
            except tk.TclError:
                pass

    def bagli_okuyuculari_guncelle(self, aygitlar: Iterable[Any]) -> None:
        bagli_portlar: set[int] = set()
        for aygit in aygitlar:
            port = getattr(aygit, "usb_port", None)
            if isinstance(port, int):
                bagli_portlar.add(port)
                continue
            # Eski/harici cagrilar icin metinden yakalamaya calis
            port = self._metinden_port_bul(str(aygit))
            if isinstance(port, int):
                bagli_portlar.add(port)
        self._usb_port_gostergesini_guncelle(bagli_portlar)

    def _merkez_mesaj_goster(
        self,
        ust_metin: str,
        alt_metin: str = "",
        *,
        renk: str = RENK_METIN_KOYU,
        tarih_goster: bool = True,
        ust_pady: Optional[tuple[int, int]] = None,
    ) -> None:
        try:
            self.baslik_etiket.configure(text=ust_metin, fg=renk)
            self.baslik_etiket.pack_configure(
                pady=ust_pady or (KIOSK_BASLIK_PADY1, KIOSK_BASLIK_PADY2)
            )
            if tarih_goster:
                self.tarih_saat_kutu.pack(fill=tk.X)
            else:
                self.tarih_saat_kutu.pack_forget()
            self.orta_okuyucu_etiket.pack_forget()
            self.kart_etiket.pack_forget()
            if alt_metin:
                self.orta_okuyucu_etiket.configure(text=alt_metin, fg=renk)
                self.orta_okuyucu_etiket.pack(fill=tk.X, padx=(2, 2), pady=(6, 0))
            self.son_okuyucu_etiket.configure(text="")
            self.son_kart_etiket.configure(text="")
        except tk.TclError:
            pass

    def hazir_ekrana_gec(self) -> None:
        self._merkez_mesaj_goster(
            METIN_HAZIR,
            renk=RENK_METIN_KOYU,
            tarih_goster=True,
        )

    def islem_bekleniyor_goster(self, is_giris: bool) -> None:
        self._merkez_mesaj_goster(
            "BILGILERINIZ SORGULANIYOR",
            renk=RENK_METIN_KOYU,
            tarih_goster=False,
            ust_pady=(8, 4),
        )

    def islem_basarili_goster(self, ad_soyad: str, saat: str, is_giris: bool) -> None:
        ad = (ad_soyad or "").strip() or "KULLANICI"
        islem_saati = (saat or "").strip() or datetime.now().strftime("%H:%M")
        if is_giris:
            metin = (
                "SAYIN %s\n%s saati itibari ile GIRIS isleminiz kaydedildi"
                % (ad, islem_saati)
            )
        else:
            metin = (
                "SAYIN %s\n%s saati itibari ile CIKIS isleminiz kaydedildi"
                % (ad, islem_saati)
            )
        self._merkez_mesaj_goster(
            metin,
            renk=RENK_METIN_KOYU,
            tarih_goster=False,
            ust_pady=(8, 4),
        )

    def merkez_hata_goster(self, metin: str) -> None:
        self._merkez_mesaj_goster(
            metin,
            renk=RENK_UYARI,
            tarih_goster=False,
            ust_pady=(8, 4),
        )

    def sunucu_mesaji_goster(self, metin: str) -> None:
        self._merkez_mesaj_goster(
            metin,
            renk=RENK_METIN_KOYU,
            tarih_goster=False,
            ust_pady=(8, 4),
        )

    def _bekleme_ekranina_don(self) -> None:
        self._son_okuma_after_id = None
        self.hazir_ekrana_gec()

    def son_okumayi_guncelle(
        self, okuyucu_kisa: str, kart_numarasi: str
    ) -> None:
        self._iptal_son_okuma_zamanlayici()
        metin = "%s: %s\n%s: %s" % (
            METIN_OKUYUCU_ETIKET,
            okuyucu_kisa,
            METIN_KART_ETIKET,
            kart_numarasi,
        )
        self._merkez_mesaj_goster(
            metin,
            renk=BOOTSTRAP_PRIMARY,
            tarih_goster=False,
            ust_pady=(8, 4),
        )
        ms = int(max(SON_OKUMA_GOSTERIM_SANIYE, 0.5) * 1000)
        self._son_okuma_after_id = self.kok.after(ms, self._bekleme_ekranina_don)

    def uyari_metni(self, metin: str) -> None:
        self.merkez_hata_goster(metin)
