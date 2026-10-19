#!/bin/bash
# Kiosk ekraninda NetworkManager / masaustu baglanti istekleri ve
# bildirim pencerelerini engeller (idempotent). INTERNET GEREKMEZ.
#
# Kullanim:
#   sudo ./scripts/kiosk_ui_engelle.sh          # kalici kurulum
#   ./scripts/kiosk_ui_engelle.sh --runtime     # sadece calisan popup'lari kapat
set -euo pipefail

TABBY_USER="${TABBY_USER:-tabby}"
TABBY_HOME="${TABBY_HOME:-/home/${TABBY_USER}}"
TABBY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_ONLY=0
case "${1:-}" in
  --runtime|-r) RUNTIME_ONLY=1 ;;
esac

_log() { echo "[kiosk-ui] $*" >&2; }

_kill_popup_surecleri() {
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
  pkill -x dhcpcd-gtk 2>/dev/null || true
  # Pi OS panel ag eklentisi WiFi popup uretir — paneli kiosk'ta kapat
  pkill -x wf-panel-pi 2>/dev/null || true
  pkill -x wf-panel 2>/dev/null || true
  pkill -x lxpanel 2>/dev/null || true
  pkill -x lxpanel-pi 2>/dev/null || true
  pkill -f 'lxpanel-pi' 2>/dev/null || true
  pkill -x lxpanelctl 2>/dev/null || true
  pkill -x pcmanfm 2>/dev/null || true
}

if [ "$RUNTIME_ONLY" = "1" ]; then
  _kill_popup_surecleri
  exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
  _log "kalici kurulum icin root gerekli: sudo $0"
  exit 1
fi

# --- 1) NetworkManager: connectivity popup ---
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/99-tabby-no-connectivity-check.conf <<'EOF'
[connectivity]
enabled=false

[main]
no-auto-default=*
auth-polkit=false

[connection]
connection.auth-retries=0
EOF

if [ -f "${TABBY_ROOT}/scripts/tabby-wifi-mac.conf" ]; then
  cp "${TABBY_ROOT}/scripts/tabby-wifi-mac.conf" \
    /etc/NetworkManager/conf.d/tabby-wifi-mac.conf
fi

# --- 2) nm-applet / bildirim autostart kapat ---
_disable_autostart() {
  local name="$1"
  local src=""
  for d in /etc/xdg/autostart /usr/share/applications; do
    if [ -f "${d}/${name}" ]; then
      src="${d}/${name}"
      break
    fi
  done
  local dest="${TABBY_HOME}/.config/autostart/${name}"
  mkdir -p "${TABBY_HOME}/.config/autostart"
  if [ -n "$src" ]; then
    cp -a "$src" "$dest" 2>/dev/null || true
  else
    cat > "$dest" <<EOF
[Desktop Entry]
Type=Application
Name=${name%.desktop}
EOF
  fi
  if grep -q '^Hidden=' "$dest" 2>/dev/null; then
    sed -i 's/^Hidden=.*/Hidden=true/' "$dest"
  else
    echo "Hidden=true" >> "$dest"
  fi
  if grep -q '^X-GNOME-Autostart-enabled=' "$dest" 2>/dev/null; then
    sed -i 's/^X-GNOME-Autostart-enabled=.*/X-GNOME-Autostart-enabled=false/' "$dest"
  else
    echo "X-GNOME-Autostart-enabled=false" >> "$dest"
  fi
  if ! grep -q '^NoDisplay=' "$dest" 2>/dev/null; then
    echo "NoDisplay=true" >> "$dest"
  else
    sed -i 's/^NoDisplay=.*/NoDisplay=true/' "$dest"
  fi
}

for app in \
  nm-applet.desktop \
  nm-tray.desktop \
  blueman.desktop \
  blueman-applet.desktop \
  xfce4-notifyd.desktop \
  notification-daemon.desktop \
  mate-notification-daemon.desktop \
  lxqt-notificationd.desktop \
  dunst.desktop \
  mako.desktop \
  polkit-gnome-authentication-agent-1.desktop \
  lxpolkit.desktop \
  xfce-polkit.desktop \
  gnome-keyring-pkcs11.desktop \
  gnome-keyring-secrets.desktop \
  gnome-keyring-ssh.desktop \
  dhcpcd-gtk.desktop \
  wf-panel-pi.desktop \
  lxpanel.desktop \
  lxpanel-pi.desktop \
  pcmanfm-desktop.desktop
do
  _disable_autostart "$app"
done

mkdir -p /etc/xdg/autostart
for app in nm-applet.desktop nm-tray.desktop blueman-applet.desktop \
           dhcpcd-gtk.desktop wf-panel-pi.desktop lxpanel.desktop lxpanel-pi.desktop; do
  cat > "/etc/xdg/autostart/${app}" <<EOF
[Desktop Entry]
Type=Application
Name=${app%.desktop}
Exec=/bin/true
Hidden=true
X-GNOME-Autostart-enabled=false
NoDisplay=true
EOF
done

# lxpanel-pi binary stub (Pi OS X11 paneli — WiFi popup kaynagi)
if [ -x /usr/bin/lxpanel-pi ] && [ ! -f /usr/bin/lxpanel-pi.tabby-real ]; then
  mv /usr/bin/lxpanel-pi /usr/bin/lxpanel-pi.tabby-real
  cat > /usr/bin/lxpanel-pi <<'EOF'
#!/bin/sh
# Tabby kiosk: lxpanel-pi engellendi (WiFi baglanti popup).
exit 0
EOF
  chmod 755 /usr/bin/lxpanel-pi
  _log "lxpanel-pi stub"
fi
if [ -x /usr/bin/lxpanel ] && [ ! -f /usr/bin/lxpanel.tabby-real ]; then
  # Sadece pi varyanti yoksa genel lxpanel'i de stub'la
  if [ ! -x /usr/bin/lxpanel-pi ] && [ ! -f /usr/bin/lxpanel-pi.tabby-real ]; then
    :
  fi
fi

if [ -x /usr/bin/nm-applet ] && [ ! -f /usr/bin/nm-applet.tabby-real ]; then
  mv /usr/bin/nm-applet /usr/bin/nm-applet.tabby-real
  cat > /usr/bin/nm-applet <<'EOF'
#!/bin/sh
# Tabby kiosk: nm-applet bilerek engellendi.
exit 0
EOF
  chmod 755 /usr/bin/nm-applet
  _log "nm-applet stub"
fi

# --- 3) Pi OS panel (wf-panel-pi / lxpanel) — WiFi popup kaynagi ---
# Panel kiosk'ta gereksiz; ag eklentisi sifre/baglanti penceresi acar.
if id "$TABBY_USER" >/dev/null 2>&1; then
  sudo -u "$TABBY_USER" mkdir -p \
    "${TABBY_HOME}/.config/autostart" \
    "${TABBY_HOME}/.config/labwc" \
    "${TABBY_HOME}/.config/wayfire" \
    "${TABBY_HOME}/.config/wf-panel-pi" \
    "${TABBY_HOME}/.config/lxpanel/LXDE-pi/panels" \
    "${TABBY_HOME}/.config/xfce4/xfconf/xfce-perchannel-xml" \
    2>/dev/null || true

  # labwc / LXDE-pi autostart: panel baslatma satirlarini etkisizlestir
  for as in \
    "${TABBY_HOME}/.config/labwc/autostart" \
    /etc/xdg/labwc/autostart \
    /usr/share/labwc/autostart
  do
    [ -f "$as" ] || continue
    if [ "$as" != "${TABBY_HOME}/.config/labwc/autostart" ]; then
      if [ ! -f "${TABBY_HOME}/.config/labwc/autostart" ]; then
        cp "$as" "${TABBY_HOME}/.config/labwc/autostart" 2>/dev/null || true
      fi
    fi
  done
  if [ -f "${TABBY_HOME}/.config/labwc/autostart" ]; then
    sed -i -E \
      's|^[[:space:]]*(wf-panel-pi|wf-panel|lxpanel-pi|lxpanel|pcmanfm).*|# tabby-kiosk: &|' \
      "${TABBY_HOME}/.config/labwc/autostart" 2>/dev/null || true
  else
    cat > "${TABBY_HOME}/.config/labwc/autostart" <<'EOF'
#!/bin/sh
# Tabby kiosk: masaustu paneli bilerek baslatilmiyor (WiFi popup engeli).
EOF
    chmod +x "${TABBY_HOME}/.config/labwc/autostart"
  fi

  # X11 Pi OS: ~/.config/lxsession/LXDE-pi/autostart
  for lxas_src in \
    "${TABBY_HOME}/.config/lxsession/LXDE-pi/autostart" \
    /etc/xdg/lxsession/LXDE-pi/autostart
  do
    [ -f "$lxas_src" ] || continue
    mkdir -p "${TABBY_HOME}/.config/lxsession/LXDE-pi"
    if [ "$lxas_src" != "${TABBY_HOME}/.config/lxsession/LXDE-pi/autostart" ]; then
      if [ ! -f "${TABBY_HOME}/.config/lxsession/LXDE-pi/autostart" ]; then
        cp "$lxas_src" "${TABBY_HOME}/.config/lxsession/LXDE-pi/autostart" 2>/dev/null || true
      fi
    fi
  done
  LXAS="${TABBY_HOME}/.config/lxsession/LXDE-pi/autostart"
  if [ -f "$LXAS" ]; then
    sed -i -E \
      's|^[[:space:]]*@?(lxpanel-pi|lxpanel|wf-panel-pi|pcmanfm).*|# tabby-kiosk: &|' \
      "$LXAS" 2>/dev/null || true
  else
    mkdir -p "$(dirname "$LXAS")"
    # Sistem dosyasini kopyala + panel satirlarini kapat
    if [ -f /etc/xdg/lxsession/LXDE-pi/autostart ]; then
      cp /etc/xdg/lxsession/LXDE-pi/autostart "$LXAS"
      sed -i -E \
        's|^[[:space:]]*@?(lxpanel-pi|lxpanel|wf-panel-pi|pcmanfm).*|# tabby-kiosk: &|' \
        "$LXAS" 2>/dev/null || true
    fi
  fi

  # wayfire defaults: panel autostart kapat
  for wf in \
    "${TABBY_HOME}/.config/wayfire.ini" \
    /etc/wayfire/defaults.ini \
    /usr/share/wayfire/templates/wayfire.ini
  do
    [ -f "$wf" ] || continue
    if [ "$wf" != "${TABBY_HOME}/.config/wayfire.ini" ] && \
       [ ! -f "${TABBY_HOME}/.config/wayfire.ini" ]; then
      cp "$wf" "${TABBY_HOME}/.config/wayfire.ini" 2>/dev/null || true
    fi
  done
  if [ -f "${TABBY_HOME}/.config/wayfire.ini" ]; then
    sed -i -E \
      's|^(autostart[0-9]*[[:space:]]*=[[:space:]]*.*wf-panel[^[:space:]]*)|# tabby-kiosk: \1|' \
      "${TABBY_HOME}/.config/wayfire.ini" 2>/dev/null || true
  fi

  # wf-panel-pi.ini: network widget cikar (panel yine de baslarsa)
  for WF_INI in \
    "${TABBY_HOME}/.config/wf-panel-pi.ini" \
    "${TABBY_HOME}/.config/wf-panel-pi/wf-panel-pi.ini"
  do
    [ -f "$WF_INI" ] || continue
    python3 - "$WF_INI" <<'PY' 2>/dev/null || true
import re, sys
path = sys.argv[1]
try:
    text = open(path, encoding="utf-8").read()
except Exception:
    raise SystemExit(0)
def scrub(val):
    parts = [p.strip() for p in re.split(r"[,\s]+", val) if p.strip()]
    drop = {"network", "bluetooth", "tray", "notify", "smenu"}
    return " ".join(p for p in parts if p.lower() not in drop)
out = []
for line in text.splitlines():
    m = re.match(r"^(\s*widgets_(?:left|center|right)\s*=\s*)(.*)$", line, re.I)
    if m:
        out.append(m.group(1) + scrub(m.group(2)))
    else:
        out.append(line)
open(path, "w", encoding="utf-8").write("\n".join(out) + ("\n" if text.endswith("\n") else ""))
PY
  done

  # Eski LXDE panel: network applet kaldir
  for pan in "${TABBY_HOME}/.config/lxpanel/LXDE-pi/panels/panel" \
             "${TABBY_HOME}/.config/lxpanel/LXDE/panels/panel"; do
    [ -f "$pan" ] || continue
    python3 - "$pan" <<'PY' 2>/dev/null || true
import re, sys
path = sys.argv[1]
try:
    text = open(path, encoding="utf-8").read()
except Exception:
    raise SystemExit(0)
# Plugin blogunu sil: type=network / wireless / bluetooth
text2 = re.sub(
    r"Plugin\s*\{\s*type\s*=\s*(network|wireless|bluetooth|tray)[^}]*\}",
    "",
    text,
    flags=re.I | re.S,
)
if text2 != text:
    open(path, "w", encoding="utf-8").write(text2)
PY
  done

  if command -v gsettings >/dev/null 2>&1; then
    sudo -u "$TABBY_USER" dbus-run-session -- gsettings set \
      org.gnome.desktop.notifications show-banners false 2>/dev/null || true
  fi

  cat > "${TABBY_HOME}/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-notifyd.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-notifyd" version="1.0">
  <property name="do-not-disturb" type="bool" value="true"/>
</channel>
EOF

  chown -R "${TABBY_USER}:${TABBY_USER}" \
    "${TABBY_HOME}/.config/autostart" \
    "${TABBY_HOME}/.config/labwc" \
    "${TABBY_HOME}/.config/wayfire.ini" \
    "${TABBY_HOME}/.config/wf-panel-pi.ini" \
    "${TABBY_HOME}/.config/wf-panel-pi" \
    "${TABBY_HOME}/.config/lxpanel" \
    "${TABBY_HOME}/.config/xfce4" \
    2>/dev/null || true
fi

# --- 4) Polkit ---
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/49-tabby-kiosk-network.rules <<EOF
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 &&
        subject.user == "${TABBY_USER}") {
        return polkit.Result.YES;
    }
});
EOF

mkdir -p /etc/polkit-1/localauthority/50-local.d
cat > /etc/polkit-1/localauthority/50-local.d/49-tabby-kiosk-network.pkla <<EOF
[Tabby kiosk NetworkManager]
Identity=unix-user:${TABBY_USER}
Action=org.freedesktop.NetworkManager.*
ResultAny=yes
ResultInactive=yes
ResultActive=yes
EOF

# --- 5) NM secret agent (GUI sifre penceresini kaynaktan iptal) ---
if [ -f "${TABBY_ROOT}/scripts/nm_secret_agent_iptal.py" ]; then
  chmod +x "${TABBY_ROOT}/scripts/nm_secret_agent_iptal.py" 2>/dev/null || true
  if [ -f "${TABBY_ROOT}/systemd/tabby-nm-secret-agent.service" ]; then
    sed "s|/home/tabby|${TABBY_HOME}|g; s|/home/tabby/tabby_kiosk|${TABBY_ROOT}|g" \
      "${TABBY_ROOT}/systemd/tabby-nm-secret-agent.service" \
      > /etc/systemd/system/tabby-nm-secret-agent.service
  fi
fi

# --- 6) Popup bekci + secret agent servisleri ---
if [ -f "${TABBY_ROOT}/systemd/tabby-kiosk-popup-bekci.service" ]; then
  sed "s|/home/tabby|${TABBY_HOME}|g; s|/home/tabby/tabby_kiosk|${TABBY_ROOT}|g" \
    "${TABBY_ROOT}/systemd/tabby-kiosk-popup-bekci.service" \
    > /etc/systemd/system/tabby-kiosk-popup-bekci.service
  chmod +x "${TABBY_ROOT}/scripts/kiosk_popup_bekci.sh" 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable tabby-kiosk-popup-bekci.service 2>/dev/null || true
systemctl enable tabby-nm-secret-agent.service 2>/dev/null || true
systemctl restart tabby-kiosk-popup-bekci.service 2>/dev/null || true
systemctl restart tabby-nm-secret-agent.service 2>/dev/null || true
_log "popup bekci + nm secret agent aktif"

# --- 7) Hemen kapat ---
_kill_popup_surecleri

if systemctl is-active NetworkManager >/dev/null 2>&1; then
  systemctl reload NetworkManager 2>/dev/null || true
fi

_log "tamam (internet gerekmedi). Panel/WiFi popup engellendi."
