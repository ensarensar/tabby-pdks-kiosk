# Tabby kart okuyucu — saha dağıtım (cihaz 35 canlı kopyası)

Bu klasör **13.08.2026** tarihinde çalışan Raspberry (`192.168.35.6`) uygulamasından alındı.

Tam disk `.img` klonu **kullanmayın**. Önceki image’in çalışmamasının nedeni buydu: klonlanan kartta bu cihaza özel IP/WiFi, eksik LCD `speed=`, boot’ta takılan `apply-config` ve bazen ters `rotate` birlikte geliyordu. Beyaz ekran da buradan çıkıyordu.

Doğru yöntem: **temiz Raspberry Pi OS + bu `tabby_kiosk` klasörü + bir kurulum scripti**.

## Klasör

| Yol | Ne |
|-----|----|
| `tabby_kiosk/` | Çalışan uygulama (video URL, ekran mesajı, LCD speed düzeltmesi dahil) |
| `referans/config.txt` | Bu Pi’de **çalışan** boot satırı: `dtoverlay=waveshare35c:rotate=270,speed=16000000` |
| `referans/waveshare35c.dtbo` | LCD overlay dosyası (pakette `tabby_kiosk/assets/` içinde de var) |
| `referans/config.ornek.json` | Admin’den gönderilecek ayar örneği (`reboot_after_apply: false`) |

## Yeni Pi’ye kurulum (önerilen)

Raspberry Pi Imager:

- Raspberry Pi OS **64-bit Desktop**
- Kullanıcı: `tabby`, SSH açık
- SD yaz → Pi aç → SSH

Mac’ten (bu klasörün içinden):

```bash
cd /Users/ensaralemdaroglu/Desktop/masaUstuMAc/projelerim/tabby-kartokuyucu-35
rsync -avz --exclude '__pycache__' --exclude '*.pyc' \
  tabby_kiosk/ tabby@PI_IP:~/tabby_kiosk/
```

Pi’de:

```bash
ssh tabby@PI_IP
sudo cp ~/tabby_kiosk/assets/waveshare35c.dtbo /boot/firmware/overlays/waveshare35c.dtbo
sudo bash ~/tabby_kiosk/scripts/master_kiosk_hazirla.sh
sudo reboot
```

Açılıştan sonra LCD’de kiosk görünmeli. Ağ/IP/SSID **Admin → PDKS cihazları → Kaydet** ile bu cihaza özel gönderilir. Postman/admin gövdesinde **`reboot_after_apply: false`** olsun (true beyaz ekran riski).

## Neden tam image bozuluyordu?

1. **LCD SPI hızı** — overlay’de `speed=16000000` yoksa ekran beyaz kalır. Eski master script bunu yazmıyordu.
2. **Yön** — çalışan cihaz `rotate=270`. Eski script varsayılan `90` yazıyordu.
3. **Aynı IP / aynı WiFi profili** — klonlanan her kart aynı adresi kapıyordu.
4. **Boot apply** — `tabby-apply-config-boot` zaman aşımı overlay’i tekrar bozabiliyordu.

Bu pakette master script artık `rotate=270,speed=16000000` yazar.

## SD→SD klon (isteğe bağlı, ikinci adım)

Sadece **bir master Pi**’yi yukarıdaki yöntemle kurup **test ettikten sonra**:

```bash
ssh tabby@MASTER_IP
sudo bash ~/tabby_kiosk/scripts/altin_imaz_hazirlik.sh
sudo poweroff
```

SD’yi çıkarıp SD→SD kopyalayın. Klon **açılınca** Admin’den o cihaza özel IP/SSID verin. Canlı 35 numaralı cihazın kartını bu script ile silmeyin; saha cihazını bozar.

## Kontrol

Çalışan referans overlay:

```
dtoverlay=waveshare35c:rotate=270,speed=16000000
```

Video: `https://10.85.1.83:8000/api/pdks-cihazlari/tabby/video`  
Kart: `https://10.85.1.83:8000/tabby-kiosk-kartokuma`
