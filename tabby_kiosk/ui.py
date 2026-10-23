# -*- coding: utf-8 -*-
"""
Tabby kiosk ekrani (v1.5.0 tasarim).

Referans 480x320; daha buyuk ekranlarda orantili buyur.

  +--------------------------------------------------+
  | tabby                               09:25        |  ust bant
  |                                23.10.2026 Cuma   |
  |--------------------------------------------------|
  |  KARTINIZI OKUTUN               +-----------+    |
  |  alt metin                      |    QR     |    |  govde
  |  [<- GIRIS] [CIKIS ->]          | caption   |    |
  |                                 +-----------+    |
  |--------------------------------------------------|
  | cihaz . ag . ip                  o Giris o Cikis |  durum satiri
  +--------------------------------------------------+

Bekleme modu: yalniz tabby + buyuk QR + kisa yazi.
Genel API (main.py): hazir_ekrana_gec, islem_bekleniyor_goster,
islem_basarili_goster, merkez_hata_goster, sunucu_mesaji_goster,
son_okumayi_guncelle, uyari_metni, bagli_okuyuculari_guncelle,
qr_paneli_baslat, bekleme_moduna_gec, bekleme_modundan_cik.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime
import tkinter as tk
from tkinter import font as tkfont
from typing import Any, Iterable, Optional

from config import (
    CIKIS_USB_PORT,
    FONT_AILE,
    GELISTIRME_ESCAPE_CIKIS,
    GIRIS_USB_PORT,
    KIOSK_IMLEC_GIZLE,
    KIOSK_PENCERE_USTTE,
    METIN_KART_ETIKET,
    METIN_OKUYUCU_ETIKET,
    SON_OKUMA_GOSTERIM_SANIYE,
    TAM_EKRAN,
    TURKCE_GUNLER,
)
from device_info import oku_ekran_bilgisi

LOG = logging.getLogger(__name__)


def _renk(ad: str, varsayilan: str) -> str:
    v = os.environ.get(ad, "").strip()
    return v if re.fullmatch(r"#[0-9a-fA-F]{6}", v or "") else varsayilan


# Tabby kurumsal palet
LACIVERT = _renk("TABBY_UI_LACIVERT", "#00096b")
LACIVERT_KOYU = _renk("TABBY_UI_LACIVERT_KOYU", "#00054a")
INDIGO = _renk("TABBY_UI_INDIGO", "#2b36a8")
BEYAZ = "#ffffff"
SOLUK = "#b9bfe8"
KIRMIZI_B = "#fd3550"
YESIL = "#16a34a"
KIRMIZI = "#dc2626"
SARI = "#f59e0b"

METIN_ISTEM = "Kartınızı okutun"
METIN_ISTEM_ALT = "Girişte soldaki, çıkışta sağdaki okuyucuyu kullanın"
METIN_QR = "Kartını mı unuttun?\nTabby ile okut"
METIN_QR_BEKLEME = "Kartını mı unuttun? QR okut"
REF_W, REF_H = 480.0, 320.0


class KioskArayuz:
    def __init__(self, kok: tk.Tk) -> None:
        self.kok = kok
        self.kok.title("Tabby Kiosk")
        self.kok.configure(bg=LACIVERT)
        if TAM_EKRAN:
            self.kok.attributes("-fullscreen", True)
        self.kok.attributes("-topmost", KIOSK_PENCERE_USTTE)
        if GELISTIRME_ESCAPE_CIKIS:
            self.kok.bind("<Escape>", lambda e: self.kok.quit())

        self._olcek = 1.0
        self._son_boyut = (0, 0)
        self._son_okuma_after_id: Optional[Any] = None
        self._bekleme = False
        self._qr_jeton = ""
        self._qr_foto = None
        self._qr_bekleme_foto = None
        self._qr_gorunur = False
        self._qr_taban_getir = None
        self._bagli_portlar: set[int] = set()

        f = FONT_AILE
        self.f_marka = tkfont.Font(family=f, size=22, weight="bold")
        self.f_saat = tkfont.Font(family=f, size=20, weight="bold")
        self.f_tarih = tkfont.Font(family=f, size=9)
        self.f_istem = tkfont.Font(family=f, size=21, weight="bold")
        self.f_alt = tkfont.Font(family=f, size=9)
        self.f_rozet = tkfont.Font(family=f, size=10, weight="bold")
        self.f_yon = tkfont.Font(family=f, size=13, weight="bold")
        self.f_qr = tkfont.Font(family=f, size=9, weight="bold")
        self.f_durum = tkfont.Font(family=f, size=8)
        self.f_bekleme_marka = tkfont.Font(family=f, size=30, weight="bold")
        self.f_bekleme_qr = tkfont.Font(family=f, size=12, weight="bold")

        # ---------- aktif ekran ----------
        self.aktif = tk.Frame(kok, bg=LACIVERT)
        ust = tk.Frame(self.aktif, bg=LACIVERT_KOYU)
        ust.pack(side=tk.TOP, fill=tk.X)
        self._marka(ust, self.f_marka, LACIVERT_KOYU).pack(side=tk.LEFT, padx=(12, 0), pady=4)
        saat_kutu = tk.Frame(ust, bg=LACIVERT_KOYU)
        saat_kutu.pack(side=tk.RIGHT, padx=(0, 12), pady=2)
        self.saat_etiket = tk.Label(saat_kutu, bg=LACIVERT_KOYU, fg=BEYAZ, font=self.f_saat)
        self.saat_etiket.pack(anchor=tk.E)
        self.tarih_etiket = tk.Label(saat_kutu, bg=LACIVERT_KOYU, fg=SOLUK, font=self.f_tarih)
        self.tarih_etiket.pack(anchor=tk.E)

        alt = tk.Frame(self.aktif, bg=LACIVERT_KOYU)
        alt.pack(side=tk.BOTTOM, fill=tk.X)
        self.bilgi_etiket = tk.Label(alt, bg=LACIVERT_KOYU, fg=SOLUK, font=self.f_durum, anchor=tk.W)
        self.bilgi_etiket.pack(side=tk.LEFT, padx=(10, 4), pady=3, fill=tk.X, expand=True)
        self._port_noktalari: dict[int, tuple[tk.Canvas, str]] = {}
        for port, ad in ((CIKIS_USB_PORT, "Çıkış"), (GIRIS_USB_PORT, "Giriş")):
            tk.Label(alt, text=ad, bg=LACIVERT_KOYU, fg=SOLUK, font=self.f_durum).pack(side=tk.RIGHT, padx=(2, 10))
            cv = tk.Canvas(alt, width=10, height=10, bg=LACIVERT_KOYU, highlightthickness=0, bd=0)
            cv.pack(side=tk.RIGHT)
            self._port_noktalari[port] = (cv, ad)

        govde = tk.Frame(self.aktif, bg=LACIVERT)
        govde.pack(fill=tk.BOTH, expand=True)
        govde.columnconfigure(0, weight=1)
        govde.columnconfigure(1, weight=0)
        govde.rowconfigure(0, weight=1)

        self.sol = tk.Frame(govde, bg=LACIVERT)
        self.sol.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=(8, 8))
        ic = tk.Frame(self.sol, bg=LACIVERT)
        ic.place(relx=0.0, rely=0.5, anchor="w", relwidth=1.0)
        self.rozet = tk.Label(ic, bg=INDIGO, fg=BEYAZ, font=self.f_rozet, padx=8, pady=1)
        self.istem = tk.Label(ic, text=METIN_ISTEM, bg=LACIVERT, fg=BEYAZ, font=self.f_istem,
                              justify=tk.LEFT, anchor=tk.W)
        self.istem.pack(fill=tk.X, anchor=tk.W)
        self.istem_alt = tk.Label(ic, text=METIN_ISTEM_ALT, bg=LACIVERT, fg=SOLUK, font=self.f_alt,
                                  justify=tk.LEFT, anchor=tk.W)
        self.istem_alt.pack(fill=tk.X, anchor=tk.W, pady=(2, 8))
        self.yonler = tk.Frame(ic, bg=LACIVERT)
        self.yonler.pack(fill=tk.X, anchor=tk.W)
        self._yon(self.yonler, "←  GİRİŞ", YESIL).pack(side=tk.LEFT, padx=(0, 6))
        self._yon(self.yonler, "ÇIKIŞ  →", KIRMIZI).pack(side=tk.LEFT)
        self._ic = ic

        self.qr_kart = tk.Frame(govde, bg=BEYAZ)
        self.qr_resim = tk.Label(self.qr_kart, bg=BEYAZ, bd=0)
        self.qr_resim.pack(padx=6, pady=(6, 2))
        self.qr_yazi = tk.Label(self.qr_kart, text=METIN_QR, bg=BEYAZ, fg=LACIVERT,
                                font=self.f_qr, justify=tk.CENTER)
        self.qr_yazi.pack(padx=6, pady=(0, 6))

        # ---------- bekleme ekrani ----------
        self.bekleme = tk.Frame(kok, bg=LACIVERT)
        bic = tk.Frame(self.bekleme, bg=LACIVERT)
        bic.place(relx=0.5, rely=0.5, anchor="center")
        self._marka(bic, self.f_bekleme_marka, LACIVERT).pack(pady=(0, 6))
        self.b_qr_kutu = tk.Frame(bic, bg=BEYAZ)
        self.b_qr_resim = tk.Label(self.b_qr_kutu, bg=BEYAZ, bd=0)
        self.b_qr_resim.pack(padx=8, pady=8)
        self.b_qr_kutu.pack()
        self.b_yazi = tk.Label(bic, text=METIN_QR_BEKLEME, bg=LACIVERT, fg=BEYAZ, font=self.f_bekleme_qr)
        self.b_yazi.pack(pady=(6, 0))
        self.b_istem = tk.Label(bic, text=METIN_ISTEM, bg=LACIVERT, fg=BEYAZ, font=self.f_bekleme_qr)

        self.aktif.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.kok.bind("<Configure>", self._boyut_degisti)
        if KIOSK_IMLEC_GIZLE:
            self._imlec_gizle(self.kok)
        self._port_ciz()
        self._saat_dongusu()
        self._bilgi_dongusu()
        self.hazir_ekrana_gec()

    # ---------- yardimcilar ----------
    @staticmethod
    def _marka(ust: tk.Misc, font: tkfont.Font, bg: str) -> tk.Frame:
        kutu = tk.Frame(ust, bg=bg)
        for parca, renk in (("tab", BEYAZ), ("b", KIRMIZI_B), ("y", BEYAZ)):
            tk.Label(kutu, text=parca, font=font, fg=renk, bg=bg, bd=0, padx=0).pack(side=tk.LEFT)
        return kutu

    def _yon(self, ust: tk.Misc, metin: str, renk: str) -> tk.Label:
        return tk.Label(ust, text=metin, bg=renk, fg=BEYAZ, font=self.f_yon, padx=12, pady=6)

    @staticmethod
    def _imlec_gizle(widget: tk.Misc) -> None:
        try:
            widget.configure(cursor="none")
            for c in widget.winfo_children():
                KioskArayuz._imlec_gizle(c)
        except tk.TclError:
            pass

    def _boyut_degisti(self, _evt=None) -> None:
        w, h = self.kok.winfo_width(), self.kok.winfo_height()
        if (w, h) == self._son_boyut or w < 120:
            return
        self._son_boyut = (w, h)
        s = max(0.6, min(w / REF_W, h / REF_H))
        self._olcek = s
        for fnt, taban in (
            (self.f_marka, 22), (self.f_saat, 20), (self.f_tarih, 9), (self.f_istem, 21),
            (self.f_alt, 9), (self.f_rozet, 10), (self.f_yon, 13), (self.f_qr, 9),
            (self.f_durum, 8), (self.f_bekleme_marka, 30), (self.f_bekleme_qr, 12),
        ):
            fnt.configure(size=max(7, int(round(taban * s))))
        sol_w = int(w - self.qr_kenar() - 50 * s) if self._qr_gorunur else int(w - 30 * s)
        for lbl in (self.istem, self.istem_alt):
            lbl.configure(wraplength=max(120, sol_w))
        if self._qr_jeton:
            self._qr_ciz(self._qr_jeton)

    def qr_kenar(self) -> int:
        return int(108 * self._olcek)

    def bekleme_qr_kenar(self) -> int:
        return int(170 * self._olcek)

    # ---------- saat / bilgi ----------
    def _saat_dongusu(self) -> None:
        try:
            n = datetime.now()
            self.saat_etiket.configure(text=n.strftime("%H:%M"))
            self.tarih_etiket.configure(text="%s %s" % (n.strftime("%d.%m.%Y"), TURKCE_GUNLER[n.weekday()]))
        except tk.TclError:
            return
        self.kok.after(1000, self._saat_dongusu)

    def _bilgi_dongusu(self) -> None:
        try:
            b = oku_ekran_bilgisi()
            self.bilgi_etiket.configure(text="%s  ·  %s  ·  %s" % (b["cihaz_adi"], b["baglanti_metin"], b["ip"]))
        except Exception:
            pass
        self.kok.after(3000, self._bilgi_dongusu)

    # ---------- okuyucu durum ----------
    def _port_ciz(self) -> None:
        for port, (cv, _ad) in self._port_noktalari.items():
            try:
                cv.delete("all")
                renk = "#22c55e" if port in self._bagli_portlar else "#6b7280"
                cv.create_oval(1, 1, 9, 9, fill=renk, outline="")
            except tk.TclError:
                pass

    @staticmethod
    def _metinden_port_bul(metin: str) -> Optional[int]:
        m = re.search(r"\b(?:usb|port)\s*([0-9]+)\b", metin or "", flags=re.IGNORECASE)
        return int(m.group(1)) if m else None

    def bagli_okuyuculari_guncelle(self, aygitlar: Iterable[Any]) -> None:
        portlar: set[int] = set()
        for a in aygitlar:
            p = getattr(a, "usb_port", None)
            if not isinstance(p, int):
                p = self._metinden_port_bul(str(a))
            if isinstance(p, int):
                portlar.add(p)
        self._bagli_portlar = portlar
        self._port_ciz()

    # ---------- mesaj durumlari ----------
    def _goster(self, metin: str, alt: str = "", rozet: str = "", rozet_renk: str = INDIGO,
                renk: str = BEYAZ, yonler: bool = False) -> None:
        self.bekleme_modundan_cik(hazira_don=False)
        try:
            self.rozet.pack_forget()
            if rozet:
                self.rozet.configure(text=rozet, bg=rozet_renk)
                self.rozet.pack(anchor=tk.W, pady=(0, 4), before=self.istem)
            self.istem.configure(text=metin, fg=renk)
            self.istem_alt.configure(text=alt)
            if yonler:
                self.yonler.pack(fill=tk.X, anchor=tk.W)
            else:
                self.yonler.pack_forget()
        except tk.TclError:
            pass

    def hazir_ekrana_gec(self) -> None:
        self._goster(METIN_ISTEM, METIN_ISTEM_ALT, yonler=True)

    def islem_bekleniyor_goster(self, is_giris: bool) -> None:
        self._goster("Bilgileriniz sorgulanıyor…", "Lütfen bekleyin",
                     rozet="GİRİŞ" if is_giris else "ÇIKIŞ", rozet_renk=YESIL if is_giris else KIRMIZI)

    def islem_basarili_goster(self, ad_soyad: str, saat: str, is_giris: bool) -> None:
        ad = (ad_soyad or "").strip() or "Personel"
        islem_saati = (saat or "").strip() or datetime.now().strftime("%H:%M")
        etiket = "Giriş" if is_giris else "Çıkış"
        self._goster("Sn %s" % ad, "%s kaydınız %s ile kaydedilmiştir." % (etiket, islem_saati),
                     rozet="✓ %s" % etiket.upper(), rozet_renk=YESIL if is_giris else KIRMIZI)

    def merkez_hata_goster(self, metin: str) -> None:
        self._goster(metin, rozet="UYARI", rozet_renk=SARI, renk=BEYAZ)

    def sunucu_mesaji_goster(self, metin: str) -> None:
        self._goster(metin, rozet="BİLGİ", rozet_renk=INDIGO)

    def uyari_metni(self, metin: str) -> None:
        self.merkez_hata_goster(metin)

    def _iptal_son_okuma_zamanlayici(self) -> None:
        if self._son_okuma_after_id is not None:
            try:
                self.kok.after_cancel(self._son_okuma_after_id)
            except tk.TclError:
                pass
            self._son_okuma_after_id = None

    def son_okumayi_guncelle(self, okuyucu_kisa: str, kart_numarasi: str) -> None:
        self._iptal_son_okuma_zamanlayici()
        self._goster("%s: %s" % (METIN_KART_ETIKET, kart_numarasi),
                     "%s: %s" % (METIN_OKUYUCU_ETIKET, okuyucu_kisa), rozet="OKUNDU")
        ms = int(max(SON_OKUMA_GOSTERIM_SANIYE, 0.5) * 1000)
        self._son_okuma_after_id = self.kok.after(ms, self.hazir_ekrana_gec)

    # ---------- bekleme modu ----------
    def bekleme_moduna_gec(self) -> None:
        if self._bekleme:
            return
        self._bekleme = True
        self._bekleme_qr_guncelle()
        self.bekleme.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bekleme.lift()

    def bekleme_modundan_cik(self, hazira_don: bool = True) -> None:
        if not self._bekleme:
            return
        self._bekleme = False
        self.bekleme.place_forget()
        if hazira_don:
            self.hazir_ekrana_gec()

    def bekleme_modunda_mi(self) -> bool:
        return self._bekleme

    def _bekleme_qr_guncelle(self) -> None:
        if self._qr_gorunur and self._qr_bekleme_foto is not None:
            self.b_qr_resim.configure(image=self._qr_bekleme_foto)
            self.b_istem.pack_forget()
            self.b_qr_kutu.pack(before=self.b_yazi)
            self.b_yazi.pack(pady=(6, 0))
        else:
            self.b_qr_kutu.pack_forget()
            self.b_yazi.pack_forget()
            self.b_istem.pack(pady=(10, 0))

    # ---------- QR (DEVICE_SPEC 5) ----------
    def qr_paneli_baslat(self, taban_getir) -> None:
        """taban_getir() -> 'https://sunucu:port'. QR 403/401'de gizli kalir."""
        self._qr_taban_getir = taban_getir
        self._qr_iste()

    def _qr_iste(self) -> None:
        def _isci() -> None:
            import qr_ekran

            try:
                sonuc = qr_ekran.jeton_iste(self._qr_taban_getir() or "")
            except Exception as e:  # pragma: no cover
                sonuc = qr_ekran.QrSonuc("hata", sonraki_s=qr_ekran.HATA_TEKRAR_S, mesaj=str(e))
            try:
                self.kok.after(0, lambda: self._qr_uygula(sonuc))
            except Exception:
                pass

        threading.Thread(target=_isci, name="tabby-qr", daemon=True).start()

    def _qr_ciz(self, jeton: str) -> bool:
        import qr_ekran

        img = qr_ekran.qr_resmi(jeton, self.qr_kenar())
        bimg = qr_ekran.qr_resmi(jeton, self.bekleme_qr_kenar())
        if img is None or bimg is None:
            return False
        from PIL import ImageTk

        self._qr_foto = ImageTk.PhotoImage(img)  # eski cizim burada birakilir
        self._qr_bekleme_foto = ImageTk.PhotoImage(bimg)
        self.qr_resim.configure(image=self._qr_foto)
        if self._bekleme:
            self.b_qr_resim.configure(image=self._qr_bekleme_foto)
        return True

    def _qr_uygula(self, sonuc) -> None:
        if sonuc.durum == "ok" and self._qr_ciz(sonuc.jeton):
            self._qr_jeton = sonuc.jeton
            if not self._qr_gorunur:
                self._qr_gorunur = True
                self.qr_kart.grid(row=0, column=1, sticky="e", padx=(0, 12), pady=8)
                self._son_boyut = (0, 0)
                self._boyut_degisti()
        else:
            if sonuc.mesaj:
                LOG.info("QR gizli (%s): %s", sonuc.durum, sonuc.mesaj)
            self._qr_gizle()
        if self._bekleme:
            self._bekleme_qr_guncelle()
        self.kok.after(int(sonuc.sonraki_s * 1000), self._qr_iste)

    def _qr_gizle(self) -> None:
        if self._qr_gorunur:
            self.qr_kart.grid_forget()
            self.qr_resim.configure(image="")
            self._qr_foto = None
            self._qr_bekleme_foto = None
            self._qr_jeton = ""
            self._qr_gorunur = False
            self._son_boyut = (0, 0)
            self._boyut_degisti()
