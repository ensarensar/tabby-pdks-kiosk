#!/bin/bash
# =============================================================================
# SAHA MASTER HAZIRLIK — hizli / temiz / tutarli boot
# =============================================================================
# Temiz Raspberry Pi OS (64-bit Desktop) + Tabby dosyalari yuklendikten SONRA
# bir kez calistirin. Clone almadan once test edin, sonra altin_imaz_hazirlik.sh
#
#   sudo bash ~/tabby_kiosk/scripts/master_kiosk_hazirla.sh
#
# Bu script bilerek "az servis, hizli acilis, saha tutarliligi" hedefler.
# cloud-init / NFS / ModemManager / boot'ta uzun eth bekleyen oneshot KAPALI.
# =============================================================================
set -euo pipefail

TABBY_USER="${TABBY_USER:-tabby}"
TABBY_HOME="/home/${TABBY_USER}"
TABBY_ROOT="${TABBY_INSTALL_DIR:-${TABBY_HOME}/tabby_kiosk}"
WAVESHARE_ROTATE="${TABBY_WAVESHARE_ROTATE:-270}"
WAVESHARE_SPEED="${TABBY_WAVESHARE_SPEED:-16000000}"

_log() { echo "[master-hazir] $*" >&2; }
_die() { _log "HATA: $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || _die "root gerekli: sudo $0"
[ -d "$TABBY_ROOT" ] || _die "Tabby yok: $TABBY_ROOT — once pi_guncelle / dosya kopyala"

_log "=== 1/7 cloud-init ve boot takilmalari kapat ==="
systemctl disable --now \
  cloud-init.service cloud-init-local.service \
  cloud-config.service cloud-final.service 2>/dev/null || true
systemctl mask cloud-init.service cloud-init-local.service \
  cloud-config.service cloud-final.service 2>/dev/null || true
mkdir -p /etc/cloud
touch /etc/cloud/cloud-init.disabled
# Imager nocloud seed (bootfs bagliysa; degilse sessiz)
for seed in /boot/firmware/user-data /boot/user-data \
            /boot/firmware/meta-data /boot/meta-data; do
  if [ -f "$seed" ] && [ ! -f "${seed}.bak-disabled" ]; then
    mv "$seed" "${seed}.bak-disabled" || true
  fi
done
# cmdline cloud-init=disabled
for cmd in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  [ -f "$cmd" ] || continue
  if ! grep -q 'cloud-init=disabled' "$cmd"; then
    # tek satir dosya
    sed -i 's/[[:space:]]*$//' "$cmd"
    printf ' cloud-init=disabled' >> "$cmd"
    echo >> "$cmd"
  fi
done

_log "=== 2/7 gereksiz / yavas servisler kapat ==="
# NFS / rpc — saha kiosk'ta yok; boot'ta takilma yapanlar
# plymouth-quit-wait — temiz Desktop'ta 60-90 sn boot bekletiyordu
# NetworkManager-wait-online — kiosk offline calisir; online bekleme gereksiz
for u in \
  rpcbind.service rpcbind.socket \
  nfs-client.target \
  nfs-blkmap.service \
  proc-fs-nfsd.mount \
  remote-fs.target \
  ModemManager.service \
  bluetooth.service \
  hciuart.service \
  cups.service cups.socket cups.path \
  cups-browsed.service \
  apt-daily.timer apt-daily-upgrade.timer \
  plymouth-quit-wait.service \
  plymouth-start.service \
  plymouth-read-write.service \
  NetworkManager-wait-online.service
do
  systemctl disable --now "$u" 2>/dev/null || true
  systemctl mask "$u" 2>/dev/null || true
done
# Splash/quiet kaldir — plymouth beklemesi + daha temiz boot log
for cmd in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  [ -f "$cmd" ] || continue
  sed -i 's/ quiet//g; s/ splash//g; s/ plymouth.ignore-serial-consoles//g' "$cmd" || true
done

_log "=== 3/7 grafik: X11 + autologin + Waveshare fb0 ==="
systemctl set-default graphical.target 2>/dev/null || true
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_boot_behaviour B4 2>/dev/null || true
  raspi-config nonint do_wayland W1 2>/dev/null || true
fi
if [ -f /etc/lightdm/lightdm.conf ] && ! grep -q '^logind-check-graphical=false' /etc/lightdm/lightdm.conf; then
  sed -i '/^\[LightDM\]/a logind-check-graphical=false' /etc/lightdm/lightdm.conf || true
fi
# Waveshare fbdev: GPU/DRI yok. Stock lightdm Wants=dev-dri-card0 → ~75-90 sn bekler.
# Drop-in Wants= sifirlama yetmez; tam override gerekli.
cat > /etc/systemd/system/lightdm.service <<'EOF'
[Unit]
Description=Light Display Manager (Tabby fbdev — no DRI wait)
Documentation=man:lightdm(1)
After=systemd-user-sessions.service

[Service]
ExecStart=/usr/sbin/lightdm
Restart=always
BusName=org.freedesktop.DisplayManager

[Install]
Alias=display-manager.service
WantedBy=graphical.target
EOF
systemctl mask plymouth-quit.service 2>/dev/null || true
systemctl daemon-reload 2>/dev/null || true
systemctl enable lightdm.service 2>/dev/null || true

# Waveshare: SPI LCD = /dev/fb0; vc4 kapat; fbturbo yerine fbdev
CFG=""
for aday in /boot/firmware/config.txt /boot/config.txt; do
  [ -f "$aday" ] && CFG="$aday" && break
done
if [ -n "$CFG" ]; then
  sed -i 's/^dtoverlay=vc4-kms-v3d/#dtoverlay=vc4-kms-v3d/' "$CFG" || true
  sed -i '/^display_rotate=/d; /^lcd_rotate=/d' "$CFG" || true
  grep -q '^dtparam=spi=on' "$CFG" || echo 'dtparam=spi=on' >> "$CFG"
  if ! grep -qE '^dtoverlay=waveshare35c' "$CFG"; then
    cat >> "$CFG" <<EOF

# Tabby Waveshare 3.5 LCD C (saha master)
dtoverlay=waveshare35c:rotate=${WAVESHARE_ROTATE},speed=${WAVESHARE_SPEED}
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=87
hdmi_cvt=480 320 60 6 0 0 0
hdmi_drive=2
EOF
  else
    sed -i -E "s|^dtoverlay=waveshare35c.*|dtoverlay=waveshare35c:rotate=${WAVESHARE_ROTATE},speed=${WAVESHARE_SPEED}|" "$CFG"
  fi
fi
# Overlay dosyasi: once paket icindeki, sonra LCD-show
for dtbo_src in \
  "${TABBY_ROOT}/assets/waveshare35c.dtbo" \
  "${TABBY_HOME}/LCD-show/waveshare35c-overlay.dtb"
do
  if [ ! -f /boot/firmware/overlays/waveshare35c.dtbo ] && [ -f "$dtbo_src" ]; then
    cp -f "$dtbo_src" /boot/firmware/overlays/waveshare35c.dtbo
    _log "overlay kopyalandi: $dtbo_src"
    break
  fi
done
mkdir -p /usr/share/X11/xorg.conf.d
cat > /usr/share/X11/xorg.conf.d/99-fbturbo.conf <<'EOF'
Section "Device"
    Identifier "Waveshare FBDEV"
    Driver "fbdev"
    Option "fbdev" "/dev/fb0"
EndSection
EOF

_log "=== 4/7 USB input izinleri ==="
usermod -aG input,video,plugdev,dialout "$TABBY_USER" 2>/dev/null || true
cat > /etc/udev/rules.d/99-tabby-input.rules <<'EOF'
KERNEL=="event*", SUBSYSTEM=="input", MODE="0660", GROUP="input"
EOF
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

_log "=== 5/7 Tabby servisleri (sade) ==="
chmod +x "${TABBY_ROOT}/scripts/"*.sh 2>/dev/null || true
# Unit kur + UI engel (ekran_yonu burada tekrar calisir)
TABBY_WAVESHARE_ROTATE="$WAVESHARE_ROTATE" \
  bash "${TABBY_ROOT}/scripts/tabby_servisleri_kur.sh"

# Boot'ta UZUN bekleyen / gereksiz Tabby oneshot'lari kapat
# - failover boot: 15s eth bekler → saha WiFi-only'de her acilista gecikme
# - ilk-acilis: sadece clone sonrasi bir kez (maskeleme yok; enable kalsin ama genelde idle)
systemctl disable tabby-network-failover.service 2>/dev/null || true
# Watch yeter; eth/wifi olaylari dispatcher + watch ile gider
mkdir -p /etc/systemd/system/tabby-network-failover-watch.service.d
cat > /etc/systemd/system/tabby-network-failover-watch.service.d/saha.conf <<'EOF'
[Service]
Environment=TABBY_ETH_BEKLEME_S=3
Environment=TABBY_FAILOVER_ARALIK_S=8
Environment=TABBY_WIFI_RETRY_S=20
EOF

# apply-config-boot: config yoksa hizli cikmali; timeout kisalt
mkdir -p /etc/systemd/system/tabby-apply-config-boot.service.d
cat > /etc/systemd/system/tabby-apply-config-boot.service.d/saha.conf <<'EOF'
[Service]
TimeoutStartSec=45
EOF

systemctl daemon-reload
systemctl enable tabby-kiosk.service tabby-network-failover-watch.service \
  tabby-config-agent.service tabby-apply-config-boot.service \
  tabby-kiosk-popup-bekci.service tabby-nm-secret-agent.service 2>/dev/null || true
systemctl restart tabby-config-agent.service tabby-network-failover-watch.service \
  tabby-kiosk.service tabby-kiosk-popup-bekci.service tabby-nm-secret-agent.service \
  2>/dev/null || true

_log "=== 6/7 NetworkManager sade ==="
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/tabby-saha.conf <<'EOF'
[main]
plugins=ifupdown,keyfile
dns=default

[device]
wifi.scan-rand-mac-address=no

[connection-wifi]
mac-address-randomization=0

[connectivity]
# Internet check kiosk'ta thrash / gecikme yaratmasin
interval=0
EOF
systemctl restart NetworkManager 2>/dev/null || true

_log "=== 7/7 dogrulama ozeti ==="
_log "surum=$(tr -d '[:space:]' < "${TABBY_ROOT}/VERSION" 2>/dev/null || echo '?')"
_log "cloud-init disabled file: $(test -f /etc/cloud/cloud-init.disabled && echo OK || echo EKSIK)"
_log "fb conf:"
grep -E 'fbdev|Driver' /usr/share/X11/xorg.conf.d/99-fbturbo.conf 2>/dev/null || true
_log "config waveshare:"
grep -E 'waveshare35c|vc4-kms|spi=on' "${CFG:-/boot/firmware/config.txt}" 2>/dev/null || true
_log "tabby servis:"
systemctl is-enabled tabby-kiosk tabby-network-failover-watch tabby-config-agent \
  tabby-apply-config-boot tabby-network-failover 2>/dev/null | tr '\n' ' ' || true
echo >&2
_log "aktif:"
systemctl is-active tabby-kiosk tabby-network-failover-watch tabby-config-agent 2>/dev/null | tr '\n' ' ' || true
echo >&2

_log ""
_log "=============================================="
_log "MASTER HAZIRLIK TAMAM"
_log ""
_log "ZORUNLU TEST (clone ONCESI):"
_log "  1) sudo reboot"
_log "  2) Acilis < ~60-90 sn, Tabby kiosk ekrani gelsin"
_log "  3) Eth cekili: TELETIP WiFi denemesi (log: failover.log)"
_log "  4) Kart okuma + beyaz ekran yok (bekleme videosu dussun)"
_log "  5) Admin Configure Et ile sahaya ozel IP/SSID"
_log ""
_log "Clone icin:"
_log "  sudo ${TABBY_ROOT}/scripts/altin_imaz_hazirlik.sh"
_log "  sudo poweroff  → SD klonla"
_log "=============================================="
