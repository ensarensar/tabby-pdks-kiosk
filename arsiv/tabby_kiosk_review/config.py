# -*- coding: utf-8 -*-
"""
Uygulama sabitleri ve yollar.
Turkce gorunen metinler ASCII kaçışlari ile (kaynakta ozel karakter yok).
"""
import os

try:
    from config_store import oku_config as _oku_config
except Exception:
    _oku_config = None

PROJE_KOKU = os.path.dirname(os.path.abspath(__file__))
_KLASOR_ASSETS = os.path.join(PROJE_KOKU, "assets")


def _config_deger(anahtar: str, varsayilan: object) -> object:
    if _oku_config is None:
        return varsayilan
    try:
        cfg = _oku_config()
    except Exception:
        return varsayilan
    if not isinstance(cfg, dict):
        return varsayilan
    deger = cfg.get(anahtar, varsayilan)
    if deger in (None, ""):
        return varsayilan
    return deger


def _float_env_veya_config(env_anahtar: str, config_anahtar: str, varsayilan: float) -> float:
    ham = os.environ.get(env_anahtar)
    if ham is None:
        ham = _config_deger(config_anahtar, varsayilan)
    try:
        return float(ham)
    except (TypeError, ValueError):
        return varsayilan


def _asset_resim(env_anahtar: str, dosya: str) -> str:
    e = os.environ.get(env_anahtar, "").strip()
    return e if e else os.path.join(_KLASOR_ASSETS, dosya)


# PNG logolar (assets/ altinda)
RESIM_TABBY_LOGO = _asset_resim("TABBY_RESIM_TABBY", "tabbyLogo.png")
RESIM_GIRIS_LOGO = _asset_resim("TABBY_RESIM_GIRIS", "girisLogo.png")
RESIM_CIKIS_LOGO = _asset_resim("TABBY_RESIM_CIKIS", "cikisLogo.png")

# Son okuma vurgusu kac saniye surecek, sonra bekleme ekrani
SON_OKUMA_GOSTERIM_SANIYE = float(
    os.environ.get("TABBY_SON_OKUMA_SANIYE", "5.0")
)
# Islem mesaji/sonuc mesaji ekranda kac saniye dursun
ISLEM_MESAJ_GOSTERIM_SANIYE = float(
    os.environ.get("TABBY_ISLEM_MESAJ_SANIYE", "5.0")
)

# Kart okunmazsa bekleme videosunun devreye girecegi sure
BEKLEME_VIDEO_BASLAMA_SANIYE = _float_env_veya_config(
    "TABBY_BEKLEME_VIDEO_BASLAMA_SANIYE",
    "bekleme_video_baslama_saniye",
    180.0,
)
# Sunucu tarafindaki video 7 saniyelik dongu ile hazirlanir/oynatilir.
BEKLEME_VIDEO_DONGU_SANIYE = float(
    os.environ.get("TABBY_BEKLEME_VIDEO_DONGU_SANIYE", "7.0")
)
BEKLEME_VIDEO_PATH = os.environ.get(
    "TABBY_BEKLEME_VIDEO_PATH",
    "/tabby-pdks-video",
).strip() or "/tabby-pdks-video"

# Pencere ve tam ekran
TAM_EKRAN = os.environ.get("TABBY_TAM_EKRAN", "1") not in ("0", "false", "False")

# --- Kiosk ekran ayarlari (ortam degiskeni ile) ---


def _float(k: str, v: float) -> float:
    try:
        return float(os.environ.get(k, str(v)))
    except ValueError:
        return v


def _int(k: str, v: int) -> int:
    try:
        return int(os.environ.get(k, str(v)))
    except ValueError:
        return v


# Varsayilan: 3.5-4 inch portrait LCD (~320x480).
# Daha buyuk/yan ekranlar icin: TABBY_REF_GENISLIK/TABBY_REF_YUKSEKLIK ile ezin.

# Dis cerceve boslugu (320x480 icin dar)
KIOSK_DIS_PADX = _int("TABBY_DIS_PADX", 6)
KIOSK_DIS_PADY = _int("TABBY_DIS_PADY", 6)

# Beyaz orta panel dis boslugu (ust-alt)
KIOSK_ORTA_PADY = _int("TABBY_ORTA_PADY", 16)
# Orta panel ince cerceve: 0 = kapali, 1 = acik
KIOSK_ORTA_CERCEVE = _int("TABBY_ORTA_CERCEVE", 1)

# Font olcegi referansi (genislik x yukseklik = 320x480 portrait)
KIOSK_REF_GENISLIK = max(200, _float("TABBY_REF_GENISLIK", 320.0))
KIOSK_REF_YUKSEKLIK = max(200, _float("TABBY_REF_YUKSEKLIK", 480.0))
# Tum fontlara carpilan ek carpan (or. 1.1 = %10 buyuk)
KIOSK_FONT_CARPAN = max(0.3, _float("TABBY_FONT_CARPAN", 1.0))

# Temel font punto (320x480 portrait; buyuk ekranda REF artir veya FONT_* env ile buyutun)
FONT_AILE = os.environ.get("TABBY_FONT_AILE", "DejaVu Sans").strip() or "DejaVu Sans"
FONT_MARKA = _int("TABBY_FONT_MARKA", 13)
FONT_BASLIK = _int("TABBY_FONT_BASLIK", 22)
FONT_ORTA_OKUYUCU = _int("TABBY_FONT_ORTA", 16)
FONT_KART = _int("TABBY_FONT_KART", 34)
FONT_ALT_KART = _int("TABBY_FONT_ALT_KART", 14)
FONT_DURUM = _int("TABBY_FONT_DURUM", 9)
FONT_ANA_BUYUK = _int("TABBY_FONT_ANA", 22)
FONT_TARIH = _int("TABBY_FONT_TARIH", 13)
FONT_GUN = _int("TABBY_FONT_GUN", 13)
FONT_SAAT = _int("TABBY_FONT_SAAT", 34)
FONT_PANEL_BASLIK = _int("TABBY_FONT_PANEL", 12)

# Logo PNG thumbnail (320x480 iki sutun; yukseklik sinirli)
LOGO_TABBY_MAX_W = _int("TABBY_LOGO_TABBY_MAX_W", 140)
LOGO_TABBY_MAX_H = _int("TABBY_LOGO_TABBY_MAX_H", 42)
LOGO_PANEL_MAX_W = _int("TABBY_LOGO_PANEL_MAX_W", 300)
LOGO_PANEL_MAX_H = _int("TABBY_LOGO_PANEL_MAX_H", 140)

# Alt bilgi bandi ic padding
KIOSK_ALT_PADX = _int("TABBY_ALT_PADX", 8)
KIOSK_ALT_PADY = _int("TABBY_ALT_PADY", 6)

# Alt logo satiri: ust bosluk buyuk = metin alani genisler, logolar asagi kayar
KIOSK_ALT_IKI_PADY1 = _int("TABBY_ALT_IKI_PADY1", 14)
KIOSK_ALT_IKI_PADY2 = _int("TABBY_ALT_IKI_PADY2", 2)
# Ust lacivert alan ile alt beyaz panel arasindaki yumusak gecis yuksekligi
KIOSK_ALT_GRADYAN_H = _int("TABBY_ALT_GRADYAN_H", 12)
# Iki panel arasi yarim bosluk (grid padx toplami)
KIOSK_PANEL_GAP = _int("TABBY_PANEL_GAP", 6)
# Merkez baslik dikey bosluk
KIOSK_BASLIK_PADY1 = _int("TABBY_BASLIK_PADY1", 4)
KIOSK_BASLIK_PADY2 = _int("TABBY_BASLIK_PADY2", 6)
# Ust logo satiri alt bosluk
KIOSK_UST_PADY_ALT = _int("TABBY_UST_PADY_ALT", 4)
# Canvas yedek panel yuksekligi (PNG yokken)
KIOSK_PANEL_CANVAS_H = _int("TABBY_PANEL_CANVAS_H", 68)

# Pencere her zaman ustte (dikkat: diger pencerelerin uzerine biner)
KIOSK_PENCERE_USTTE = os.environ.get("TABBY_PENCERE_USTTE", "0") in (
    "1",
    "true",
    "True",
)

# Imleci gizle (destekleyen Tk kurulumlarinda)
KIOSK_IMLEC_GIZLE = os.environ.get("TABBY_IMLEC_GIZLE", "0") in (
    "1",
    "true",
    "True",
)

# Renkleri ortamdan ez (hex, ornek: export TABBY_RENK_ARKA=#0f172a)
def _renk_env(anahtar: str, varsayilan: str) -> str:
    v = os.environ.get(anahtar, "").strip()
    return v if v else varsayilan


# Gelistirme: Escape ile cikis (uretimde kapali tutun)
GELISTIRME_ESCAPE_CIKIS = os.environ.get("TABBY_GELISTIRME_CIKIS", "0") in (
    "1",
    "true",
    "True",
)

# Okuyucu tarama araligi (saniye); USB tak-cikar icin dusuk tutulabilir
OKUYUCU_YENIDEN_TARAMA_SANIYE = float(
    os.environ.get("TABBY_OKUYUCU_TARAMA", "1.0")
)

# Son tustan bu kadar ms sonra buffer otomatik gonderilir (Enter gelmeyen okuyucular)
OKUYUCU_BOS_BEKLEME_MS = int(os.environ.get("TABBY_OKUYUCU_TIMEOUT_MS", "180"))
# Okuyucu aygitini grab et (1=acik, 0=kapali). Kart tuslarinin video/tarayiciya gitmesini engeller.
OKUYUCU_GRAB_AKTIF = os.environ.get("TABBY_OKUYUCU_GRAB", "1") in ("1", "true", "True")

# Fiziksel USB port rolleri
GIRIS_USB_PORT = _int("TABBY_GIRIS_USB_PORT", 1)
CIKIS_USB_PORT = _int("TABBY_CIKIS_USB_PORT", 3)

# 1 ise her tusa INFO log (hata ayiklama)
TABBY_DEBUG_TUS = os.environ.get("TABBY_DEBUG_TUS", "0") in ("1", "true", "True")

# Ana klavyeyi elemek icin isim icinde gecen parcalar (kucuk harf)
HARIC_OKUYUCU_ISIM_PARCALARI = (
    "pwr button",
    "power button",
    "sleep button",
    "video bus",
    "cec",
    "vc4",
    "hdmi",
)

# Sadece bu alt dizelerden biri isimde geciyorsa dahil et (bos = tum uygun klavyeler)
SADECE_ISIM_ICERIR = tuple(
    x.strip().lower()
    for x in os.environ.get("TABBY_SADECE_ISIM", "").split(",")
    if x.strip()
)

# Gorunen metinler
METIN_ANA_SATIR1 = "L\u00dcTFEN KART\u0130N\u0130Z\u0130"
METIN_ANA_SATIR2 = "OKUTUNUZ"
METIN_HAZIR = "L\u00dcTFEN \u0130LG\u0130L\u0130 Y\u00d6NE KARTINIZI OKUTUNUZ"
METIN_BEKLEYINIZ = "L\u00dcTFEN BEKLEY\u0130N\u0130Z"
METIN_GIRIS = "G\u0130R\u0130\u015e"
METIN_CIKIS = "\u00c7\u0130K\u0130\u015e"
METIN_BASLIK_OKU = "%s\n%s" % (METIN_ANA_SATIR1, METIN_ANA_SATIR2)
METIN_OKUYUCU_BEKLENIYOR = "Okuyucu bekleniyor"
METIN_OKUYUCU_ETIKET = "Okuyucu"
METIN_KART_ETIKET = "Kart No"
METIN_BAGLI_CIHAZLAR = "Bagl\u0131 USB okuyucular"
METIN_SON_OKUMA = "Son okuma"

# datetime.weekday(): 0=Pazartesi ... 6=Pazar
TURKCE_GUNLER = (
    "PAZARTES\u0130",
    "SALI",
    "\u00c7AR\u015eAMBA",
    "PER\u015eEMBE",
    "CUMA",
    "CUMARTES\u0130",
    "PAZAR",
)

# Arayuz renkleri (TABBY_RENK_* ile ezilebilir)
RENK_ARKA = _renk_env("TABBY_RENK_ARKA", "#0b1f3a")
RENK_ARKA_UST = _renk_env("TABBY_RENK_ARKA_UST", "#0b1f3a")
RENK_YUZEY = _renk_env("TABBY_RENK_YUZEY", "#f3f4f6")
RENK_METIN = _renk_env("TABBY_RENK_METIN", "#212529")
RENK_VURGULU = _renk_env("TABBY_RENK_VURGULU", "#0d6efd")
RENK_UYARI = _renk_env("TABBY_RENK_UYARI", "#ca8a04")
RENK_BEYAZ = _renk_env("TABBY_RENK_BEYAZ", "#ffffff")
BOOTSTRAP_PRIMARY = _renk_env("TABBY_RENK_PRIMARY", "#0d6efd")
BOOTSTRAP_DANGER = _renk_env("TABBY_RENK_DANGER", "#dc3545")
RENK_METIN_KOYU = _renk_env("TABBY_RENK_METIN_KOYU", "#ffffff")
RENK_GIRIS_YESIL = _renk_env("TABBY_RENK_GIRIS", "#22c55e")
RENK_CIKIS_KIRMIZI = _renk_env("TABBY_RENK_CIKIS", "#ef4444")
KIOSK_ORTA_CERCEVE_RENK = _renk_env("TABBY_RENK_ORTA_CERCEVE", "#dee2e6")
