#!/bin/bash
# Altin imaj almadan ONCE calistirin: cihaza ozel verileri temizler.
# Kullanim: sudo ./scripts/altin_imaz_hazirlik.sh
set -euo pipefail

TABBY_USER="${TABBY_USER:-tabby}"
TABBY_HOME="/home/${TABBY_USER}"
MARKER="/var/lib/tabby-kiosk/.ilk_acilis_bekliyor"

_log() { echo "[altin-imaj] $*" >&2; }
_die() { _log "HATA: $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || _die "root olarak calistirin: sudo $0"

_log "Cihaza ozel veriler temizleniyor..."

systemctl stop tabby-kiosk.service 2>/dev/null || true

# cloud-init tekrar acilmasin (klon sonrasi takilma)
mkdir -p /etc/cloud
touch /etc/cloud/cloud-init.disabled
systemctl disable --now cloud-init cloud-init-local cloud-config cloud-final 2>/dev/null || true
systemctl mask cloud-init cloud-init-local cloud-config cloud-final 2>/dev/null || true

# Config ve offline veritabani
rm -f /var/lib/tabby-kiosk/config.json
rm -f /var/lib/tabby-kiosk/tabby_offline.db
rm -f /var/lib/tabby-kiosk/failover.status /var/lib/tabby-kiosk/failover.log 2>/dev/null || true
rm -f "${TABBY_HOME}/.config/tabby-kiosk/config.json"
rm -f "${TABBY_HOME}/.config/tabby-kiosk/device_info.json"
rm -f "${TABBY_HOME}/tabby_kiosk/device_info.json" 2>/dev/null || true
rm -rf /var/lib/tabby-kiosk/updates 2>/dev/null || true

# NetworkManager tabby + gecici hotspot profilleri (klon cihaz kendi config'ini alsin)
if command -v nmcli >/dev/null 2>&1; then
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    case "$name" in
      tabby-*|netplan-*|Ensar*|Wired*) nmcli connection delete "$name" 2>/dev/null || true ;;
    esac
  done < <(nmcli -t -f NAME connection show 2>/dev/null || true)
fi

# Machine ID ve SSH (klon sonrasi cakisma olmasin)
rm -f /etc/machine-id
rm -f /var/lib/dbus/machine-id

rm -f /etc/ssh/ssh_host_* 2>/dev/null || true
ssh-keygen -A 2>/dev/null || true

# Hostname sablon
hostnamectl set-hostname tabby-template 2>/dev/null || echo "tabby-template" > /etc/hostname

# Ilk acilis isareti (klon sonrasi benzersiz hostname uretir)
mkdir -p /var/lib/tabby-kiosk
touch "$MARKER"
chown -R "${TABBY_USER}:${TABBY_USER}" /var/lib/tabby-kiosk "${TABBY_HOME}/.config" 2>/dev/null || true

# Journal temizligi (istege bagli, imaj kucultur)
journalctl --vacuum-time=1s 2>/dev/null || true

_log ""
_log "=============================================="
_log "SD CLONE ONCESI HAZIRLIK TAMAM"
_log ""
_log "Simdi:"
_log "  1) sudo poweroff"
_log "  2) SD karti cikar → SD→SD klonla (veya dd/imager)"
_log ""
_log "Klonlanan her cihazda:"
_log "  - Ilk acilista benzersiz hostname"
_log "  - cloud-init KAPALI (takilma olmamali)"
_log "  - Admin panelden Configure Et (eth IP + TELETIP)"
_log "=============================================="
