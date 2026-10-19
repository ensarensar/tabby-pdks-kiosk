#!/bin/bash
# Mac/gelistirme makinesinden Pi'ye 1 komutla surum at + servisleri kalici kur.
# Ornek:
#   ./scripts/pi_guncelle.sh 172.16.32.50
#   ./scripts/pi_guncelle.sh tabby@192.168.35.42
set -euo pipefail

HEDEF="${1:-}"
if [ -z "$HEDEF" ]; then
  echo "Kullanim: $0 <ip|user@ip>" >&2
  echo "Ornek:   $0 172.16.32.50" >&2
  echo "         $0 tabby@192.168.35.42" >&2
  exit 1
fi
case "$HEDEF" in
  *@*) SSH_HEDEF="$HEDEF" ;;
  *) SSH_HEDEF="tabby@${HEDEF}" ;;
esac

TABBY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARENT="$(dirname "$TABBY_ROOT")"
VERSION="$(tr -d '[:space:]' < "${TABBY_ROOT}/VERSION" 2>/dev/null || echo '?')"

echo "[pi-guncelle] surum=${VERSION} -> ${SSH_HEDEF}" >&2
tar czf - -C "$PARENT" tabby_kiosk | ssh "$SSH_HEDEF" 'cd ~ && tar xzf - && sudo ~/tabby_kiosk/scripts/tabby_servisleri_kur.sh'
echo "[pi-guncelle] bitti. Dogrula: ssh ${SSH_HEDEF} 'cat ~/tabby_kiosk/VERSION && curl -s http://127.0.0.1:8080/health'" >&2
echo "[pi-guncelle] SAHA MASTER icin: ssh ${SSH_HEDEF} 'sudo bash ~/tabby_kiosk/scripts/master_kiosk_hazirla.sh && sudo reboot'" >&2
