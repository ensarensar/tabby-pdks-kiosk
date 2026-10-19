# Tabby Kiosk — Saha Master (SD Clone) Kurulum

**Amac:** Hizli acilan, tutarli, sahada dagitilabilir master SD.  
**Yontem:** SD → SD clone (img zorunlu degil).  
**Surum hedefi:** `VERSION` dosyasindaki surum (ornegin 1.4.7).

Bu akista kisayol yok. Master **test edilmeden** clone alinmaz.

---

## 0) Bu master’da bilerek KAPALI / DUZELTILEN riskler

| Risk | Ne yapildi |
|------|------------|
| cloud-init / cloud-config takilmasi | Kalici disable + mask |
| rpc-statd / NFS boot takilmasi | disable + mask |
| ModemManager WiFi gecikmesi | disable + mask |
| Boot’ta 15 sn eth failover oneshot | **kapali** (watch + dispatcher yeter) |
| Kiosk 6 saatte restart (beyaz flash) | **kaldirildi** |
| Waveshare `/dev/fb1` siyah ekran | X → `/dev/fb0` (fbdev) |
| Chromium bekleme videosu beyaz takilma | watchdog (1.4.6+) |
| MAC klonlama | **yok** (donanim MAC) |

---

## A) Temiz OS (bir kez)

### A1. Imager

- Raspberry Pi OS **64-bit Desktop**
- Kullanici: `tabby` + sifre + SSH acik
- Gecici WiFi: telefon hotspot / ofis WiFi (kurulum icin)
- Yaz → Pi’ye tak → ac

### A2. Ilk SSH — HEMEN cloud-init kapat

```bash
ssh tabby@IP
sudo systemctl disable --now cloud-init cloud-init-local cloud-config cloud-final 2>/dev/null
sudo mkdir -p /etc/cloud && sudo touch /etc/cloud/cloud-init.disabled
sudo apt-get remove -y cloud-init 2>/dev/null || true
```

### A3. Guncelleme (tek sefer, kopmadan)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

### A4. Waveshare overlay dosyasi (bir kez)

Ekran yoksa / siyahsa:

```bash
git clone --depth 1 https://github.com/waveshare/LCD-show.git ~/LCD-show
sudo cp ~/LCD-show/waveshare35c-overlay.dtb /boot/firmware/overlays/waveshare35c.dtbo
```

(Asagidaki master script overlay + fb0 + vc4 kapatmayi da yapar.)

---

## B) Tabby + master hazirlik

### B1. Mac’ten kod at

```bash
cd ".../tabby_kiosk"
./scripts/pi_guncelle.sh IP
```

### B2. Saha master script (ZORUNLU)

```bash
ssh tabby@IP
sudo bash ~/tabby_kiosk/scripts/master_kiosk_hazirla.sh
sudo reboot
```

Bu script:

- cloud-init / NFS / ModemManager / cups vb. kapatir  
- X11 + autologin  
- Waveshare `rotate=90`, X=`/dev/fb0`  
- Tabby servislerini **sade** kurar (watch acik, boot failover oneshot kapali)  
- NM rastgele MAC / connectivity check kapatir  

### B3. Clone ONCESI test checklist (hepsi GECER)

- [ ] Acilis makul surede (hedef ~60–90 sn; cloud-config / rpc takilmasi YOK)
- [ ] Tabby kiosk ekrani geliyor (“kartinizi okutunuz”)
- [ ] Eth cekili → failover.log’da TELETIP baglanti denemesi
- [ ] Eth takili + IP → WiFi kapanir / eth oncelik
- [ ] Bekleme videosu acilip dussa bile **beyazda kalmiyor** (kiosk geri geliyor)
- [ ] Kart okuma (online veya offline liste ile)
- [ ] `cat ~/tabby_kiosk/VERSION` dogru surum
- [ ] Admin **Configure Et** ile sahaya ozel IP/SSID uygulanabiliyor

**Bir madde FAIL ise clone YOK.**

---

## C) SD clone

```bash
sudo ~/tabby_kiosk/scripts/altin_imaz_hazirlik.sh
sudo poweroff
```

SD cikar → SD→SD klonla.

Klon cihazda:

1. Acilis (benzersiz hostname)
2. Gecici ag (eth veya ofis WiFi)
3. Admin panel → **Configure Et** (eth IP + TELETIP gizli SSID)
4. Reboot → saha testi

---

## D) Sahada tutarlilik kurallari

1. **Tek master surumu** dagit; karisik 1.4.5 / 1.4.6 / 1.4.7 cihaz birakma.  
2. MAC whitelist’e **donanim wlan0 MAC** yaz (klonlama yok).  
3. Personel listesi ilk online’da dolsun; offline kart icin sart.  
4. Sorunlu cihaz: `journalctl -u tabby-kiosk -b --no-pager | tail -80`  
   `tail -50 /var/lib/tabby-kiosk/failover.log`

---

## E) Acil kurtarma (Mac’te bootfs)

cloud-config yine takilirsa SD’yi Mac’te ac:

1. `cmdline.txt` sonuna `cloud-init=disabled` ekle  
2. `user-data` / `meta-data` → `.bak-disabled` yap  
3. Eject → Pi’ye tak  

---

## Servis ozeti (master sonrasi)

| Servis | Boot |
|--------|------|
| tabby-kiosk | **acik** |
| tabby-network-failover-watch | **acik** |
| tabby-config-agent | **acik** |
| tabby-apply-config-boot | acik (config yoksa hizli cikar) |
| tabby-kiosk-popup-bekci | acik |
| tabby-nm-secret-agent | acik |
| tabby-network-failover (oneshot) | **kapali** |
| cloud-init* | **kapali/mask** |
