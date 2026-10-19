#!/bin/bash
# X sunucusu hazir olana kadar bekler; sonra kiosk'u baslatir.
set -e
TABBY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DISPLAY="${DISPLAY:-:0}"

_disp="${DISPLAY#*:}"
_disp="${_disp%%.*}"
[ -z "$_disp" ] && _disp=0
X_SOCKET="/tmp/.X11-unix/X${_disp}"

# XAUTHORITY: ev otoritesi dosyasi veya bazi DM yollari
if [ -z "${XAUTHORITY:-}" ] || [ ! -f "$XAUTHORITY" ]; then
  for cand in "$HOME/.Xauthority" "/run/user/$(id -u)/gdm/Xauthority"; do
    if [ -f "$cand" ]; then
      export XAUTHORITY="$cand"
      break
    fi
  done
fi

_x_hazir() {
  [ -S "$X_SOCKET" ] || return 1
  if command -v xset >/dev/null 2>&1; then
    xset q >/dev/null 2>&1
  else
    return 0
  fi
}

X_BEKLE_MAX_S="${TABBY_X_WAIT_MAX_S:-120}"
case "$X_BEKLE_MAX_S" in
  ''|*[!0-9]*) X_BEKLE_MAX_S=120 ;;
esac
for _ in $(seq 1 "$X_BEKLE_MAX_S"); do
  if _x_hazir; then
    break
  fi
  sleep 1
done

_ntp_senkron_mu() {
  if ! command -v timedatectl >/dev/null 2>&1; then
    return 0
  fi
  _s="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)"
  [ "$_s" = "yes" ] || [ "$_s" = "1" ]
}

# Saatin yanlis acilmasini azaltmak icin NTP senkronunu bekle (varsayilan hizli).
NTP_BEKLE_MAX_S="${TABBY_NTP_WAIT_MAX_S:-5}"
case "$NTP_BEKLE_MAX_S" in
  ''|*[!0-9]*) NTP_BEKLE_MAX_S=5 ;;
esac
if [ "$NTP_BEKLE_MAX_S" -gt 0 ]; then
  for _ in $(seq 1 "$NTP_BEKLE_MAX_S"); do
    if _ntp_senkron_mu; then
      break
    fi
    sleep 1
  done
fi

# Ekran koruyucu/DPMS kapali: kiosk her zaman aktif kalsin.
if command -v xset >/dev/null 2>&1; then
  xset s off >/dev/null 2>&1 || true
  xset -dpms >/dev/null 2>&1 || true
  xset s noblank >/dev/null 2>&1 || true
fi

# Arka planda acilan baglanti istegi / NM bildirim pencerelerini kapat.
if [ -x "$TABBY_ROOT/scripts/kiosk_ui_engelle.sh" ]; then
  "$TABBY_ROOT/scripts/kiosk_ui_engelle.sh" --runtime >/dev/null 2>&1 || true
fi

cd "$TABBY_ROOT"
exec /usr/bin/python3 "$TABBY_ROOT/main.py"
