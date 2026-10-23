# Değişiklikler

## 1.5.0 (2026-10-23)
- Cihaz sırrı: sunucuya giden her istek (`/tabby-kiosk-personel-export`, kart okuma, heartbeat, bekleme videosu, QR) `X-Tabby-Cihaz` ve `X-Tabby-Cihaz-Gizli` başlıklarını taşır. Kaynak: `TABBY_CIHAZ_ID`/`TABBY_CIHAZ_GIZLI` ortamı veya `/var/lib/tabby-kiosk/cihaz_kimlik.json` (chmod 600, depoya girmez; örnek `tabby_kiosk/cihaz_kimlik.ornek.json`). Sır yoksa başlık gitmez, eski uç/allowlist davranışı sürer.
- Kartını unutanlar için QR: sağ üstte `GET /tabby-kiosk-qr?cihaz=<id>` jetonu QR olarak çizilir, ~8 sn'de yenilenir; 403 (QR kapalı) / 401'de gizlenir. `TABBY_QR_EKRAN=0` ile kapatılır.
- `requirements.txt`: `qrcode`. Kurulum: `python3-qrcode`, `python3-pil.imagetk`.
- Log: `kiosk.log` döner dosya (10 MB x 3); saniyelik "Okuyucu tarama" mesajı DEBUG. (1.4.9 cihaz 35.6'da log 1.5 GB olup diski doldurmuştu.)
- Testler: `python3 -m unittest discover -s tabby_kiosk/tests`.

## 1.4.9
- Cihaz 35 canlı kopyası.
