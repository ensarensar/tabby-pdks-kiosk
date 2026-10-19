#!/bin/bash
# Klonlanmis SD ilk acilista bir kez calisir.
set -euo pipefail

MARKER="/var/lib/tabby-kiosk/.ilk_acilis_bekliyor"
TABBY_USER="${TABBY_USER:-tabby}"
TABBY_HOME="/home/${TABBY_USER}"

_log() { echo "[ilk-acilis] $*" >&2; }

[ -f "$MARKER" ] || exit 0
[ "$(id -u)" -eq 0 ] || exit 0

_log "Ilk acilis islemleri basliyor..."

# machine-id yenile
if [ ! -s /etc/machine-id ]; then
  systemd-machine-id-setup 2>/dev/null || true
fi

# Benzersiz hostname (eth0 MAC son 3 byte)
MAC=""
for ifn in eth0 end0 enp1s0; do
  if [ -f "/sys/class/net/${ifn}/address" ]; then
    MAC="$(cat "/sys/class/net/${ifn}/address" 2>/dev/null | tr -d ':' | tail -c 7)"
    [ -n "$MAC" ] && break
  fi
done
[ -z "$MAC" ] && MAC="$(head -c 3 /dev/urandom | od -An -tx1 | tr -d ' \n' | tail -c 6)"
YENI_HOST="tabby-${MAC}"
hostnamectl set-hostname "$YENI_HOST" 2>/dev/null || echo "$YENI_HOST" > /etc/hostname

mkdir -p /var/lib/tabby-kiosk "${TABBY_HOME}/.config/tabby-kiosk" 2>/dev/null || true
chown -R "${TABBY_USER}:${TABBY_USER}" /var/lib/tabby-kiosk "${TABBY_HOME}/.config" 2>/dev/null || true

rm -f "$MARKER"
_log "Ilk acilis tamamlandi. Hostname: $YENI_HOST"
