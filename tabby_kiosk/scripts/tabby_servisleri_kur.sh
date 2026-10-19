#!/bin/bash
# Tabby servislerini kalici kur/yenile (idempotent).
# Tar deploy, OTA update veya config apply sonrasi bunu calistir —
# elle install/cp/systemctl dizisi gerekmez.
set -euo pipefail

TABBY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TABBY_HOME="${TABBY_HOME:-/home/tabby}"
SYSTEMD_SRC="${TABBY_ROOT}/systemd"
VERSION_FILE="${TABBY_ROOT}/VERSION"

_log() { echo "[tabby-servis] $*" >&2; }

if [ "$(id -u)" -ne 0 ]; then
  _log "root gerekli — sudo ile calistirin"
  exit 1
fi

_log "Kaynak: $TABBY_ROOT (surum=$(tr -d '[:space:]' < "$VERSION_FILE" 2>/dev/null || echo '?'))"

# Script izinleri
if [ -d "${TABBY_ROOT}/scripts" ]; then
  chmod +x "${TABBY_ROOT}/scripts/"*.sh 2>/dev/null || true
fi

# systemd unit'leri kiosk paketinden kur
mkdir -p /etc/systemd/system
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
  src="${SYSTEMD_SRC}/${unit}"
  [ -f "$src" ] || continue
  sed "s|/home/tabby|${TABBY_HOME}|g; s|/home/tabby/tabby_kiosk|${TABBY_ROOT}|g" \
    "$src" > "/etc/systemd/system/${unit}"
  _log "unit: $unit"
done

# NM dispatcher (eth down → wifi)
if [ -x "${TABBY_ROOT}/scripts/tabby-nm-dispatcher.sh" ]; then
  install -m 0755 "${TABBY_ROOT}/scripts/tabby-nm-dispatcher.sh" \
    /etc/NetworkManager/dispatcher.d/99-tabby-failover
  # Dispatcher icindeki SCRIPT yolunu bu kurulum köküne göre tut
  sed -i "s|/home/tabby/tabby_kiosk|${TABBY_ROOT}|g" \
    /etc/NetworkManager/dispatcher.d/99-tabby-failover
  _log "dispatcher: 99-tabby-failover"
fi

# WiFi MAC conf (varsa)
if [ -f "${TABBY_ROOT}/scripts/tabby-wifi-mac.conf" ]; then
  mkdir -p /etc/NetworkManager/conf.d
  cp "${TABBY_ROOT}/scripts/tabby-wifi-mac.conf" \
    /etc/NetworkManager/conf.d/tabby-wifi-mac.conf
fi

# Baglanti istegi / masaustu bildirim pencerelerini engelle
if [ -x "${TABBY_ROOT}/scripts/kiosk_ui_engelle.sh" ]; then
  TABBY_HOME="$TABBY_HOME" "${TABBY_ROOT}/scripts/kiosk_ui_engelle.sh" || true
fi

# Waveshare: varsa mevcut rotate'i koru; SPI speed her zaman yazilsin (yuksek hiz = beyaz LCD)
if [ -x "${TABBY_ROOT}/scripts/ekran_yonu_ayarla.sh" ]; then
  mevcut_rotate=""
  for _cfg in /boot/firmware/config.txt /boot/config.txt; do
    [ -f "$_cfg" ] || continue
    mevcut_rotate="$(grep -oE 'dtoverlay=waveshare35c:rotate=[0-9]+' "$_cfg" 2>/dev/null | head -1 | grep -oE '[0-9]+$' || true)"
    break
  done
  "${TABBY_ROOT}/scripts/ekran_yonu_ayarla.sh" \
    "${TABBY_WAVESHARE_ROTATE:-${mevcut_rotate:-270}}" || true
fi

systemctl daemon-reload

# Saha boot: watch + kiosk + agent. Boot oneshot failover (15s eth) KAPALI —
# her acilista gecikme / thrash yapardi; dispatcher + watch yeter.
systemctl enable tabby-config-agent.service 2>/dev/null || true
systemctl enable tabby-apply-config-boot.service 2>/dev/null || true
systemctl disable tabby-network-failover.service 2>/dev/null || true
systemctl enable tabby-network-failover-watch.service 2>/dev/null || true
systemctl enable tabby-kiosk.service 2>/dev/null || true
systemctl enable tabby-kiosk-popup-bekci.service 2>/dev/null || true
systemctl enable tabby-nm-secret-agent.service 2>/dev/null || true

systemctl restart tabby-config-agent.service 2>/dev/null || true
systemctl restart tabby-network-failover-watch.service 2>/dev/null || true
systemctl restart tabby-kiosk.service 2>/dev/null || true
systemctl restart tabby-kiosk-popup-bekci.service 2>/dev/null || true
systemctl restart tabby-nm-secret-agent.service 2>/dev/null || true

_log "aktif:"
systemctl is-active tabby-config-agent.service tabby-kiosk.service \
  tabby-network-failover-watch.service tabby-kiosk-popup-bekci.service \
  tabby-nm-secret-agent.service \
  2>/dev/null | tr '\n' ' ' >&2 || true
echo >&2
_log "tamam (boot failover oneshot disabled; watch aktif)"
