# Tabby Kiosk

Raspberry Pi OS Desktop uzerinde tam ekran Tkinter kiosk: PNG logolar, merkez mesaj + tarih/saat, GIRIS/CIKIS panelleri, altta USB okuyucu bilgisi.

## Donanim ve yazilim

- Raspberry Pi 4, Raspberry Pi OS (Desktop, X11 onerilir)
- 4 inch LCD veya HDMI
- USB RFID/NFC okuyucu (HID / klavye emulasyonu)
- Python 3, Tkinter, `Pillow` (PNG logolar), `evdev`, `pyudev`

---

## Kurulum adimlari (Raspberry Pi)

Asagidaki adimlari sirayla uygulayin. Kullanici adini `tabby` yerine kendi kullanicinizla degistirebilirsiniz; o zaman systemd dosyasindaki `User=` ve yollari da guncelleyin.

### 1) Sistem paketleri

```bash
sudo apt update
sudo apt install -y python3-pip python3-tk python3-pil
```

### 2) PNG logolar (`assets/`)

Asagidaki dosyalari `tabby_kiosk/assets/` icine koyun:

| Dosya | Kullanim |
|-------|----------|
| `tabbyLogo.png` | Sol ust marka |
| `girisLogo.png` | GIRIS etiketinin alti |
| `cikisLogo.png` | CIKIS etiketinin alti |

Dosya yoksa: tabby icin `tab`/`b`/`y` metin yedegi; giris/cikis icin renkli canvas yedegi gosterilir.

Istege bagli tam yol (ortam): `TABBY_RESIM_TABBY`, `TABBY_RESIM_GIRIS`, `TABBY_RESIM_CIKIS`.

Boyut limitleri: `TABBY_LOGO_TABBY_MAX_W`, `TABBY_LOGO_TABBY_MAX_H`, `TABBY_LOGO_PANEL_MAX_W`, `TABBY_LOGO_PANEL_MAX_H`.

### 3) Proje dizini

Projeyi hedefe kopyalayin (ornek):

```bash
sudo mkdir -p /home/tabby
sudo cp -r tabby_kiosk /home/tabby/
sudo chown -R tabby:tabby /home/tabby/tabby_kiosk
```

### 3.5) Cihaz bilgileri dosyasi (`device_info.json`)

Endpoint'e giden cihaz kimligi ve alt panelde gorunen bilgiler bu dosyadan okunur:

```json
{
  "cihaz_adi": "default-reader",
  "cihaz_ip": "172.16.32.50",
  "cihaz_mac": "EA:EA:C3:21:06:80"
}
```

Kalici dosya yolu varsayilan: `/home/tabby/.config/tabby-kiosk/device_info.json`  
Geriye donuk uyumluluk icin eski yol (`/home/tabby/tabby_kiosk/device_info.json`) dosyasi da okunur.
Isterseniz `TABBY_DEVICE_INFO_FILE` ile farkli yol verebilirsiniz.
`/home/tabby/.config/tabby-kiosk/config.json` dosyasi yoksa uygulama ilk calismada bu fabrika degerleri ile otomatik olusturur.

### 4) Python bagimliliklari

```bash
cd /home/tabby/tabby_kiosk
pip3 install --user -r requirements.txt
```

Sistem geneli kurulum tercih ederseniz:

```bash
sudo pip3 install -r requirements.txt
```

### 5) Input aygit izni (evdev)

Okuyucular `/dev/input/event*` uzerinden okunur. Kullaniciyi `input` grubuna ekleyin; **cikis yapip tekrar girin** (veya yeniden baslatin):

```bash
sudo usermod -aG input tabby
groups tabby
```

### 6) Elle calistirma testi

```bash
cd /home/tabby/tabby_kiosk
export DISPLAY=:0
python3 main.py
```

Gelistirme icin pencereden cikmak isterseniz: `TABBY_GELISTIRME_CIKIS=1` ve **Escape**.

### 7) Baslatma betigi (systemd ve autostart icin)

X tamamen ayaga kalkana kadar bekler; servis cok erken baslasa bile pencere acilabilir.

```bash
chmod +x /home/tabby/tabby_kiosk/scripts/kiosk_baslat.sh
```

Istege bagli (daha saglam X kontrolu): `sudo apt install -y x11-xserver-utils` (`xset`).

### 7.5) Saati NTP'den cek (onerilen, sizdeki sunucu: `10.85.1.130`)

Saatin her acilista dogru kalmasi icin cihazin sistem saati NTP ile senkron olmalidir.

```bash
sudo timedatectl set-timezone Europe/Istanbul
sudo timedatectl set-ntp false
sudo tee /etc/systemd/timesyncd.conf >/dev/null <<'EOF'
[Time]
NTP=10.85.1.130
FallbackNTP=
EOF
sudo systemctl restart systemd-timesyncd
sudo timedatectl set-ntp true
timedatectl status
timedatectl show -p NTPSynchronized --value
```

Beklenen: `NTPSynchronized=yes` (veya `1`).

Not: Bu repo icindeki `tabby-kiosk.service`, saat senkronu hedefini bekleyecek sekilde guncellenmistir (`time-sync.target` + `systemd-time-wait-sync.service`).

### 8) Otomatik baslatma — systemd (onerilen guncelleme)

Eski `graphical-session.target` tabanli birimler siklikla **hic calismaz** veya X hazir olmadan duser. Guncel birim `graphical.target` + `kiosk_baslat.sh` kullanir.

Tkinter icin grafik oturumu gerekir. **Otomatik giris (autologin)** acin (`raspi-config` veya Raspberry Pi OS ayarlari, kullanici `tabby`).

```bash
sudo cp /home/tabby/tabby_kiosk/systemd/tabby-kiosk.service /etc/systemd/system/tabby-kiosk.service
sudo nano /etc/systemd/system/tabby-kiosk.service
```

`User`, `Group`, `WorkingDirectory`, `ExecStart` (betik yolu) alanlarini kendi kullaniciniza gore kontrol edin.

```bash
sudo systemctl daemon-reload
sudo systemctl disable tabby-kiosk.service 2>/dev/null || true
sudo systemctl enable tabby-kiosk.service
sudo systemctl start tabby-kiosk.service
sudo systemctl status tabby-kiosk.service
```

Log ve hata ayiklama:

```bash
journalctl -u tabby-kiosk.service -b --no-pager
journalctl -u tabby-kiosk.service -f
```

**Servis yeniden baslatma:** `Restart=always` ile surec cokerse yeniden kalkar.

### 8.5) Cihazi 6 saatte bir otomatik reboot et (istege bagli)

Sistem saati/senkron ve uzun sureli kararlilik icin cihazin kendisini periyodik yeniden baslatabilirsiniz.

```bash
sudo cp /home/tabby/tabby_kiosk/systemd/tabby-auto-reboot.service /etc/systemd/system/
sudo cp /home/tabby/tabby_kiosk/systemd/tabby-auto-reboot.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tabby-auto-reboot.timer
sudo systemctl list-timers | rg tabby-auto-reboot
```

### 8.6) Kiosk'tan bagimsiz network config agent (onerilen saha modeli)

Bu modelde network ayarlari kiosk surecinden ayridir. Kiosk kapali olsa bile
`/tabby-config` endpoint'i calisir ve OS seviyesinde (nmcli/timedatectl) ayarlar uygulanir.

Kurulum:

```bash
sudo cp /home/tabby/tabby_kiosk/systemd/tabby-config-agent.service /etc/systemd/system/
sudo cp /home/tabby/tabby_kiosk/systemd/tabby-apply-config.service /etc/systemd/system/
sudo chmod +x /home/tabby/tabby_kiosk/scripts/apply_tabby_config.sh
sudo systemctl daemon-reload
sudo systemctl disable --now tabby-apply-config.path 2>/dev/null || true
sudo systemctl enable --now tabby-config-agent.service
sudo systemctl status tabby-config-agent.service --no-pager -l
```

Health kontrol:

```bash
curl -s http://127.0.0.1:8080/health
```

### 8.7) Uzaktan network konfigurasyonu (POST/PUT /tabby-config)

Endpoint (config-agent):

- `POST http://<cihaz-ip>:8080/tabby-config`
- `PUT  http://<cihaz-ip>:8080/tabby-config`

Bu endpoint:

1. JSON verisini dogrular ve `/home/tabby/.config/tabby-kiosk/config.json` dosyasina yazar.
2. `apply_tabby_config.sh` script'ini hemen calistirir.
3. Network/NTP/WiFi/MAC ayarlarinin OS seviyesinde uygulanmasini saglar.

Ornek:

```bash
curl -X POST "http://172.16.32.50:8080/tabby-config" \
  -H "Content-Type: application/json" \
  -d '{
    "cihaz_adi": "default-reader",
    "cihaz_ip": "172.16.32.50",
    "cihaz_mac": "EA:EA:C3:21:06:80",
    "subnet_mask": "255.255.255.0",
    "gateway": "172.16.32.1",
    "dns": "172.16.32.1,8.8.8.8",
    "ntp_server": "10.85.1.130",
    "wifi_ssid": "Ensar",
    "wifi_password": "Ensar++80",
    "wifi_ip": "172.16.32.51",
    "wifi_mac": "EA:EA:C3:21:06:81",
    "wifi_subnet_mask": "255.255.255.0",
    "wifi_gateway": "172.16.32.1",
    "wifi_dns": "172.16.32.1,8.8.8.8",
    "wifi_interface": "wlan0",
    "ethernet_interface": "eth0",
    "heartbeat_url": "http://10.85.100.8:3000/tabby-pdks-cihaz-heartbeat",
    "heartbeat_token": "cihaza-ozel-gizli-token",
    "heartbeat_interval_s": 30,
    "heartbeat_timeout_s": 120,
    "heartbeat_aktif": true,
    "bekleme_video_kullanici": "201866",
    "bekleme_video_sifre": "Ensar++80",
    "bekleme_video_login_url": "https://172.16.32.50:8443/giris",
    "bekleme_video_baslama_saniye": 180,
    "reboot_after_apply": false
  }'
```

Not:

- `reboot_after_apply=true` gelirse apply script reboot oncesi bu alani otomatik `false` yapar.
- `servis_url`/`kart_okuma_endpoint` ayarlari da ayni payload ile gonderilebilir.
- WiFi icin `wifi_ip`/`wifi_mac` verilirse `tabby-wifi` NetworkManager profili bu statik IPv4 ve MAC ile acilir. `wifi_mac` verildiginde NetworkManager MAC randomization kapatilir. `wifi_subnet_mask`, `wifi_gateway`, `wifi_dns` bos birakilirsa sirasiyla `subnet_mask`, `gateway`, `dns` degerleri kullanilir.
- `heartbeat_aktif=true`, `heartbeat_url` ve `heartbeat_token` doluysa kiosk arka planda periyodik heartbeat gonderir. `heartbeat_interval_s` bos ise 30 saniye, `heartbeat_timeout_s` bos ise 120 saniye varsayilir.
- Heartbeat endpoint'i varsayilan format: `POST /tabby-pdks-cihaz-heartbeat`. Gonderilen govde `connection_type`, `ip`, `mac`, `ssid`, `rssi`, `ethernet_ip`, `ethernet_mac`, `ethernet_dhcp`, `wifi_ip`, `wifi_mac`, `wifi_dhcp` alanlarini icerir. Header olarak hem `Authorization: Bearer <token>` hem de `X-Tabby-Heartbeat-Token: <token>` gonderilir.
- Heartbeat baglanti tipi icin once aktif default route arayuzune, sonra `ethernet_interface`/`wifi_interface` carrier durumuna bakar. WiFi bagliysa `iw` veya `iwconfig` ile SSID/RSSI okumaya calisir.
- Kiosk'un kendi ic endpoint'i varsayilan olarak kapalidir (`TABBY_REMOTE_RESTART_ENABLE=0`), cakismaz.
- Kiosk alt panelindeki cihaz IP/MAC bilgisi aktif arayuzden (eth0/wlan0) okunur; apply sonrasi reboot beklemeden yenilenir.

### 9) Alternatif: masaustu autostart (systemd calismazsa)

Bazi kurulumlarda kullanici oturumu acildiktan sonra calistirmak daha guvenilirdir:

```bash
mkdir -p /home/tabby/.config/autostart
cp /home/tabby/tabby_kiosk/autostart/tabby-kiosk.desktop /home/tabby/.config/autostart/
# .desktop icindeki Exec yolunu ve kullaniciyi duzenleyin
nano /home/tabby/.config/autostart/tabby-kiosk.desktop
```

Bu yontemde systemd servisini kapatin: `sudo systemctl disable --now tabby-kiosk.service`

### Sorun giderme: masaustu geliyor ama uygulama acilmiyor

1. **Servis durumu:** `systemctl status tabby-kiosk.service` — `failed` ise `journalctl -u tabby-kiosk.service -e` ciktisina bakin.
2. **Elle betik:** Oturumda `DISPLAY=:0 bash /home/tabby/tabby_kiosk/scripts/kiosk_baslat.sh` — aciliyorsa sorun systemd zamanlamasi veya kullanici/yol idi.
3. **Wayland:** Raspberry Pi OS Bookworm bazen Wayland kullanir; Tkinter sorun cikarabilir. `raspi-config` > Advanced > Wayland kapat / X11 secin, yeniden baslatin.
4. **Python modulleri:** `pip3 install --user -r requirements.txt` kullanici `tabby` ile calistirildi mi? systemd ayni kullanici ile calisir; `--user` kurulum dogru kullanicida olmali.
5. **Eski birim:** Daha once `graphical-session.target` ile enable ettiyseniz: `sudo rm -f /etc/systemd/system/graphical-session.target.wants/tabby-kiosk.service` ve `sudo systemctl daemon-reload`, sonra bu README'deki `graphical.target` birimini tekrar `enable` edin.

---

## Davranis ozeti

| Ozellik | Aciklama |
|--------|----------|
| Ekran | Varsayilan olcek **4 inch ~480x320** LCD; `TABBY_REF_GENISLIK` / `TABBY_REF_YUKSEKLIK` ile cozunurluk |
| Logolar | `assets/*.png` (yoksa tabby metin + canvas yedek) |
| Bekleme ekrani | LUTFEN KARTINIZI / OKUTUNUZ + tarih + saat |
| Son okuma | Ortada cok buyuk kart numarasi, okuyucu adi; altta ozet; **5 saniye** sonra otomatik bekleme ekranina doner (yeni okuma gelirse sure sifirlanir) |
| USB tak/cikar | Periyodik tarama (varsayilan 1 sn) + `pyudev` ile input olayinda aninda yenileme ve okuyucu thread yenileme |
| Cokme | Log + systemd ile surekli yeniden baslatma |

---

## Yapilandirma (ortam degiskenleri)

| Degisken | Aciklama |
|----------|----------|
| `TABBY_TAM_EKRAN` | `1` (varsayilan) veya `0` |
| `TABBY_GELISTIRME_CIKIS` | `1` ise Escape ile cikis |
| `TABBY_OKUYUCU_TARAMA` | USB listesi tarama suresi (saniye), varsayilan `1.0` |
| `TABBY_SON_OKUMA_SANIYE` | Son okuma ekraninda kalma suresi, varsayilan `5.0` |
| `TABBY_SADECE_ISIM` | Virgulle ayirilmis alt dizeler; sadece adi bunlari iceren aygitlar |
| `TABBY_OKUYUCU_TIMEOUT_MS` | Enter/Tab gelmezse son tustan sonra kac ms bekleyip karti tamamlanmis say (varsayilan `180`) |
| `TABBY_DEBUG_TUS` | `1` ise her tusa INFO log (hangi `KEY_*` geldigini gormek icin) |
| `TABBY_BEKLEME_VIDEO_BASLAMA_SANIYE` | Kart okunmazsa bekleme videosunun kac saniye sonra baslayacagi; varsayilan `180`. Config alani: `bekleme_video_baslama_saniye` |
| `TABBY_BEKLEME_VIDEO_KULLANICI`, `TABBY_BEKLEME_VIDEO_SIFRE` | Bekleme videosu icin `/giris` endpoint'ine POST atarken kullanilacak bilgiler. Config alanlari: `bekleme_video_kullanici`, `bekleme_video_sifre` |
| `TABBY_BEKLEME_VIDEO_LOGIN_URL` | Bekleme videosu oturum endpoint'i; varsayilan `https://<sunucu>:8443/giris`. Config alani: `bekleme_video_login_url` |
| `TABBY_REF_GENISLIK` | Font olcegi referans genislik (varsayilan `480`, 4" LCD) |
| `TABBY_REF_YUKSEKLIK` | Font olcegi referans yukseklik (varsayilan `320`) |
| `TABBY_DIS_PADX`, `TABBY_DIS_PADY` | Kenar bosluk (4" icin varsayilan 8 / 6) |
| `TABBY_LOGO_*` | Logo max boyutlari; `TABBY_PANEL_GAP`, `TABBY_PANEL_CANVAS_H` |

**Ornek — 7 inch / HDMI ~800x480:**  
`export TABBY_REF_GENISLIK=800` ve `export TABBY_REF_YUKSEKLIK=480` (istege bagli `TABBY_DIS_PADX=16`).

Ana klavyeyi elemek icin `config.py` icinde `HARIC_OKUYUCU_ISIM_PARCALARI` listesini genisletebilirsiniz.

### Kart okunuyor ama ekranda cikmiyor

1. Altta **bagli okuyucu listesi bos** mu? Bos ise `input` grubu ve izinleri kontrol edin; `TABBY_SADECE_ISIM` okuyucuyu disliyor olabilir.
2. Okuyucu **Enter veya Tab gondermiyor** olabilir; guncel kod **~180 ms** sessizlikten sonra otomatik tamamlar (`TABBY_OKUYUCU_TIMEOUT_MS` ile artirin/azaltin).
3. **Hata ayiklama:** `TABBY_DEBUG_TUS=1 python3 main.py` — terminalde `tus KEY_*` satirlari gorunmuyorsa olay bu aygita hic gelmiyor (baska uygulama, yanlis aygit, izin).
4. **Hex UID** (A–F harf) gonderen okuyucular desteklenir; sadece ozel karakter varsa `okuyucu_izleyici` icindeki haritaya eklenmelidir.

---

## Gelistirme (masaustu bilgisayar)

```bash
cd tabby_kiosk
python3 main.py
```

Linux disi ortamda `evdev` / `pyudev` sinirli calisir; tam test Raspberry Pi uzerinde yapilmalidir.
