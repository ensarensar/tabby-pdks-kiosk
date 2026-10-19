#!/bin/bash
# Waveshare 3.5" (waveshare35c) ekran yonunu duzeltir.
# Cakisan display_rotate/lcd_rotate satirlari kaldirilir; tek kaynak overlay rotate.
#
#   TABBY_WAVESHARE_ROTATE=90   # varsayilan (dik / portrait)
#   TABBY_WAVESHARE_ROTATE=270  # ters portrait
#   TABBY_WAVESHARE_ROTATE=0|180
#   TABBY_WAVESHARE_SPEED=16000000  # SPI; bos/yuksek hiz LCD'yi beyazda birakir
#
# Degisiklik config.txt'e yazilir; reboot sonrasi etkili olur.
#   sudo ./scripts/ekran_yonu_ayarla.sh
#   sudo ./scripts/ekran_yonu_ayarla.sh 90
set -euo pipefail

ROTATE="${1:-${TABBY_WAVESHARE_ROTATE:-90}}"
SPEED="${TABBY_WAVESHARE_SPEED:-16000000}"
case "$ROTATE" in
  0|90|180|270) ;;
  *)
    echo "[ekran-yon] Gecersiz rotate=$ROTATE (0|90|180|270)" >&2
    exit 1
    ;;
esac
if ! [[ "$SPEED" =~ ^[0-9]+$ ]]; then
  echo "[ekran-yon] Gecersiz speed=$SPEED" >&2
  exit 1
fi

OVERLAY="dtoverlay=waveshare35c:rotate=${ROTATE},speed=${SPEED}"

if [ "$(id -u)" -ne 0 ]; then
  echo "[ekran-yon] root gerekli — sudo ile calistirin" >&2
  exit 1
fi

CFG=""
for aday in /boot/firmware/config.txt /boot/config.txt; do
  if [ -f "$aday" ]; then
    CFG="$aday"
    break
  fi
done
if [ -z "$CFG" ]; then
  echo "[ekran-yon] config.txt bulunamadi" >&2
  exit 1
fi

# Cakisan sistem rotate satirlari kaldir (overlay ile birlikte kullanilmamali)
sed -i \
  -e '/^[[:space:]]*display_rotate=/d' \
  -e '/^[[:space:]]*lcd_rotate=/d' \
  "$CFG"

if grep -qE '^[[:space:]]*dtoverlay=waveshare35c' "$CFG"; then
  sed -i -E \
    "s|^[[:space:]]*dtoverlay=waveshare35c.*|${OVERLAY}|" \
    "$CFG"
else
  {
    echo ""
    echo "# Tabby Waveshare 3.5\" LCD (C)"
    echo "dtparam=spi=on"
    echo "$OVERLAY"
  } >>"$CFG"
fi

echo "[ekran-yon] $CFG -> $OVERLAY" >&2
grep -E 'waveshare35c|display_rotate|lcd_rotate' "$CFG" || true
echo "[ekran-yon] reboot sonrasi etkili olur: sudo reboot" >&2
