#!/bin/bash
# Kiosk ustune cikan WiFi/ag baglanti isteklerini surekli kapatir.
# systemd: tabby-kiosk-popup-bekci.service
set -uo pipefail

export DISPLAY="${DISPLAY:-:0}"
INTERVAL_S="${TABBY_POPUP_BEKCI_INTERVAL_S:-2}"
case "$INTERVAL_S" in
  ''|*[!0-9]*) INTERVAL_S=2 ;;
esac
[ "$INTERVAL_S" -lt 1 ] && INTERVAL_S=1

if [ -z "${XAUTHORITY:-}" ] || [ ! -f "$XAUTHORITY" ]; then
  for cand in \
    "${HOME:-/home/tabby}/.Xauthority" \
    "/home/tabby/.Xauthority" \
    "/run/user/$(id -u 2>/dev/null || echo 1000)/gdm/Xauthority"
  do
    if [ -f "$cand" ]; then
      export XAUTHORITY="$cand"
      break
    fi
  done
fi

_kill_surecler() {
  # NetworkManager GUI / secret agent / bildirim
  pkill -x nm-applet 2>/dev/null || true
  pkill -x nm-connection-editor 2>/dev/null || true
  pkill -x nm-tray 2>/dev/null || true
  pkill -f '/usr/bin/nm-applet' 2>/dev/null || true
  pkill -f 'nm-applet' 2>/dev/null || true
  pkill -x notification-daemon 2>/dev/null || true
  pkill -x xfce4-notifyd 2>/dev/null || true
  pkill -x mate-notification-daemon 2>/dev/null || true
  pkill -x dunst 2>/dev/null || true
  pkill -x mako 2>/dev/null || true
  pkill -x lxqt-notificationd 2>/dev/null || true
  pkill -x notify-osd 2>/dev/null || true
  pkill -f 'polkit-gnome-authentication-agent' 2>/dev/null || true
  pkill -f 'lxpolkit' 2>/dev/null || true
  pkill -f 'xfce-polkit' 2>/dev/null || true
  # Pi OS / genel ag diyalog yardimcilari
  pkill -x dhcpcd-gtk 2>/dev/null || true
  pkill -f 'wifi-sweet' 2>/dev/null || true
  # Pi OS panel (ag eklentisi WiFi popup uretir) — kiosk'ta kapali kalsin
  pkill -x wf-panel-pi 2>/dev/null || true
  pkill -x wf-panel 2>/dev/null || true
  pkill -x lxpanel 2>/dev/null || true
  pkill -x lxpanel-pi 2>/dev/null || true
  pkill -f 'lxpanel-pi' 2>/dev/null || true
  pkill -f '/usr/bin/lxpanel' 2>/dev/null || true
}

_kapat_pencereler() {
  # Baslik eslesmesi ile WiFi/ag istek pencerelerini kapat
  if command -v wmctrl >/dev/null 2>&1; then
    wmctrl -l 2>/dev/null | while IFS= read -r line; do
      case "$line" in
        *[Nn]etwork*|*[Ww]i-[Ff]i*|*[Ww]i[Ff]i*|*[Ww]ireless*| \
        *[Aa]uthentic*|*[Ss]ecret*|*[Pp]assword*|*[Bb]ağlant*| \
        *[Bb]aglant*|*[Aa]ğ*|*[Aa]g\ *|*[Cc]onnection\ [Rr]equired*| \
        *[Nn]etwork[Mm]anager*|nm-applet*|*[Ww]LAN*)
          wid="$(echo "$line" | awk '{print $1}')"
          [ -n "$wid" ] && wmctrl -ic "$wid" 2>/dev/null || true
          ;;
      esac
    done
  fi

  if command -v xdotool >/dev/null 2>&1; then
    for pat in \
      'Network' 'Wi-Fi' 'WiFi' 'Wireless' 'Authentication' \
      'Secrets' 'Password' 'Bağlantı' 'Baglanti' 'NetworkManager' \
      'nm-applet' 'WLAN' 'wireless network'
    do
      xdotool search --name "$pat" windowclose %@ 2>/dev/null || true
      xdotool search --classname "$pat" windowclose %@ 2>/dev/null || true
    done
  fi
}

while true; do
  _kill_surecler
  _kapat_pencereler
  sleep "$INTERVAL_S"
done
