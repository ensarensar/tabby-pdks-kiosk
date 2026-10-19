#!/bin/bash
# Sifir Raspberry Pi OS (Desktop) uzerinde Tabby kiosk tam kurulum.
# Kullanim (proje dizininden):
#   chmod +x scripts/kurulum_sifir_pi.sh
#   sudo ./scripts/kurulum_sifir_pi.sh
set -euo pipefail

TABBY_USER="${TABBY_USER:-tabby}"
TABBY_HOME="/home/${TABBY_USER}"
INSTALL_DIR="${TABBY_INSTALL_DIR:-${TABBY_HOME}/tabby_kiosk}"
KAYNAK="$(cd "$(dirname "$0")/.." && pwd)"

_log() { echo "[tabby-kurulum] $*" >&2; }
_die() { _log "HATA: $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || _die "root olarak calistirin: sudo $0"

_log "Kaynak: $KAYNAK"
_log "Hedef:  $INSTALL_DIR"

# --- 1) Kullanici ---
if ! id "$TABBY_USER" &>/dev/null; then
  _log "Kullanici olusturuluyor: $TABBY_USER"
  useradd -m -s /bin/bash "$TABBY_USER"
fi
usermod -aG input,video,plugdev,dialout "$TABBY_USER" 2>/dev/null || true

# --- 2) Sistem paketleri ---
_log "APT paketleri kuruluyor..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-pip python3-tk python3-pil \
  network-manager \
  rsync curl wget \
  x11-xserver-utils \
  xserver-xorg-video-fbturbo \
  systemd-timesyncd \
  evtest
# wmctrl/xdotool istege bagli (internet varken): popup pencere basligi kapatma
# Offline kurulumda gerekmez; kiosk_ui_engelle.sh pkill ile calisir.

# NetworkManager aktif olsun (dhcpcd ile cakisma olmasin)
systemctl enable NetworkManager 2>/dev/null || true
systemctl start NetworkManager 2>/dev/null || true

# --- 3) Uygulama dosyalari ---
_log "Dosyalar kopyalaniyor..."
mkdir -p "$(dirname "$INSTALL_DIR")"
if [ "$(readlink -f "$KAYNAK" 2>/dev/null || echo "$KAYNAK")" != "$(readlink -f "$INSTALL_DIR" 2>/dev/null || echo "$INSTALL_DIR")" ]; then
  mkdir -p "$INSTALL_DIR"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '__pycache__' \
      --exclude '*.pyc' \
      --exclude '.git' \
      --exclude 'dist' \
      "$KAYNAK/" "$INSTALL_DIR/"
  else
    cp -a "$KAYNAK/." "$INSTALL_DIR/"
  fi
fi
chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true

# --- 4) Python bagimliliklari ---
_log "pip paketleri kuruluyor..."
# Trixie/Bookworm PEP 668: --break-system-packages (--user ile birlikte)
sudo -u "$TABBY_USER" pip3 install --user --break-system-packages -r "$INSTALL_DIR/requirements.txt"

# --- 5) Kalici dizinler ---
mkdir -p /var/lib/tabby-kiosk "${TABBY_HOME}/.config/tabby-kiosk"
chown -R "${TABBY_USER}:${TABBY_USER}" /var/lib/tabby-kiosk "${TABBY_HOME}/.config" "$INSTALL_DIR"

# --- 6) systemd birimleri ---
_log "systemd servisleri kuruluyor..."
SYSTEMD_SRC="$INSTALL_DIR/systemd"
for unit in \
  tabby-config-agent.service \
  tabby-apply-config-boot.service \
  tabby-network-failover.service \
  tabby-network-failover-watch.service \
  tabby-kiosk.service \
  tabby-kiosk-popup-bekci.service \
  tabby-nm-secret-agent.service \
  tabby-ilk-acilis.service
do
  [ -f "$SYSTEMD_SRC/$unit" ] || continue
  sed "s|/home/tabby|${TABBY_HOME}|g" "$SYSTEMD_SRC/$unit" > "/etc/systemd/system/$unit"
done

# Yolları guncelle (tabby_kiosk dizin adi sabit kalabilir)
for unit in /etc/systemd/system/tabby-*.service; do
  [ -f "$unit" ] || continue
  sed -i "s|/home/tabby/tabby_kiosk|${INSTALL_DIR}|g" "$unit"
done

systemctl daemon-reload
systemctl disable tabby-apply-config.path 2>/dev/null || true

systemctl enable tabby-ilk-acilis.service
systemctl enable tabby-config-agent.service
systemctl enable tabby-apply-config-boot.service
systemctl enable tabby-network-failover.service
systemctl enable tabby-network-failover-watch.service
systemctl enable tabby-kiosk.service
systemctl enable tabby-kiosk-popup-bekci.service
systemctl enable tabby-nm-secret-agent.service

# Dispatcher + unit tazeleme (kalici failover)
if [ -x "${INSTALL_DIR}/scripts/tabby_servisleri_kur.sh" ]; then
  "${INSTALL_DIR}/scripts/tabby_servisleri_kur.sh" || true
fi

# Baglanti istegi / NM bildirim pencerelerini engelle
if [ -x "${INSTALL_DIR}/scripts/kiosk_ui_engelle.sh" ]; then
  TABBY_USER="$TABBY_USER" TABBY_HOME="$TABBY_HOME" \
    "${INSTALL_DIR}/scripts/kiosk_ui_engelle.sh" || true
fi

# --- 7) Grafik oturum (SPI ekran / lightdm) ---
_log "Grafik oturum ayarlari uygulaniyor..."
if [ -f /etc/lightdm/lightdm.conf ] && ! grep -q '^logind-check-graphical=false' /etc/lightdm/lightdm.conf; then
  sed -i '/^\[LightDM\]/a logind-check-graphical=false' /etc/lightdm/lightdm.conf
fi
systemctl set-default graphical.target 2>/dev/null || true
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_boot_behaviour B4 2>/dev/null || true
  raspi-config nonint do_wayland W1 2>/dev/null || true
fi

# --- 8) NTP (varsayilan; config apply ile guncellenir) ---
if [ ! -f /etc/systemd/timesyncd.conf.d ]; then
  mkdir -p /etc/systemd/timesyncd.conf.d 2>/dev/null || true
fi
timedatectl set-timezone Europe/Istanbul 2>/dev/null || true

_log ""
_log "=============================================="
_log "Kurulum tamamlandi."
_log ""
_log "SONRAKI ADIMLAR:"
_log "  1) Waveshare 3.5\" ekran ayarlarini tamamlayin (config.txt + fbturbo)."
_log "     Kurulum scripti lightdm/graphical.target ayarlarini uygular."
_log ""
_log "  2) Tabby admin panelden cihaz olusturup Configure Et gonderin."
_log "     (ethernet IP + MAC, TELETIP WiFi ayarlari)"
_log "     Configure sonrasi failover-watch servisi aktif edilir."
_log ""
_log "  3) Altin imaz icin:"
_log "     sudo ${INSTALL_DIR}/scripts/altin_imaz_hazirlik.sh"
_log "     sonra SD karti imajlayin (dd / Raspberry Pi Imager)."
_log ""
_log "  4) Servisleri baslatmak icin yeniden baslatin:"
_log "     sudo reboot"
_log "=============================================="
