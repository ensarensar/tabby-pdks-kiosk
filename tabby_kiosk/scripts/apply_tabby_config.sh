#!/bin/bash
# config.json verisini alir, ag/cihaz ayarlarini uygular, gerekirse reboot eder.
# Ethernet: statik IP. WiFi: yalnizca SSID/sifre (DHCP). MAC yapilandirilmaz.
set -euo pipefail

TABBY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TABBY_HOME="${TABBY_HOME:-/home/tabby}"
CONFIG_DIR="${TABBY_CONFIG_DIR:-${TABBY_HOME}/.config/tabby-kiosk}"
KALICI_CONFIG_JSON="${TABBY_KALICI_CONFIG_FILE:-/var/lib/tabby-kiosk/config.json}"
CONFIG_JSON="${TABBY_CONFIG_FILE:-$KALICI_CONFIG_JSON}"
AYNA_CONFIG_JSON="${CONFIG_DIR}/config.json"
DEVICE_INFO_JSON="${TABBY_DEVICE_INFO_FILE:-${CONFIG_DIR}/device_info.json}"
APP_SETTINGS_JSON="${TABBY_APP_SETTINGS_FILE:-${CONFIG_DIR}/app_settings.json}"
NMCLI_BIN="$(command -v nmcli || true)"

if [ ! -f "$CONFIG_JSON" ]; then
  if [ -f "$AYNA_CONFIG_JSON" ]; then
    echo "config birincil dosya yok; aynadan geri yukleniyor: $AYNA_CONFIG_JSON" >&2
    mkdir -p "$(dirname "$CONFIG_JSON")"
    cp "$AYNA_CONFIG_JSON" "$CONFIG_JSON"
    chown tabby:tabby "$CONFIG_JSON" 2>/dev/null || true
  else
    echo "Config dosyasi bulunamadi: $CONFIG_JSON"
    exit 0
  fi
fi

mkdir -p "$CONFIG_DIR" "$(dirname "$CONFIG_JSON")"

_run_maybe_timeout() {
  if command -v timeout >/dev/null 2>&1; then
    timeout 20 "$@" || true
  else
    "$@" || true
  fi
}

_wifi_nm_hazirlik() {
  local nm_conf="/etc/NetworkManager/conf.d/tabby-wifi-mac.conf"
  local kaynak="${TABBY_ROOT}/scripts/tabby-wifi-mac.conf"
  if [ -f "$kaynak" ]; then
    cp "$kaynak" "$nm_conf"
    _run_maybe_timeout systemctl reload NetworkManager
  fi
}

_wifi_profil_kur() {
  WIFI_CON_NAME="tabby-wifi"
  _wifi_nm_hazirlik
  echo "WiFi profili kuruluyor: ssid=$WIFI_SSID (DHCP)" >&2
  _run_maybe_timeout "$NMCLI_BIN" device disconnect "$WIFI_IF"
  _run_maybe_timeout "$NMCLI_BIN" connection down "$WIFI_CON_NAME"
  _run_maybe_timeout "$NMCLI_BIN" connection delete "$WIFI_CON_NAME"
  _run_maybe_timeout ip link set dev "$WIFI_IF" down

  local -a ekle_args=(
    type wifi
    ifname "$WIFI_IF"
    con-name "$WIFI_CON_NAME"
    ssid "$WIFI_SSID"
    autoconnect yes
    connection.autoconnect yes
    ipv4.method auto
    802-11-wireless.mac-address-randomization 0
  )
  if [ -n "$WIFI_PASSWORD" ]; then
    ekle_args+=(wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WIFI_PASSWORD")
  fi
  # Acik ag: wifi-sec ekleme (key-mgmt none → wep-key0 hatasi)

  if ! "$NMCLI_BIN" connection add "${ekle_args[@]}"; then
    echo "HATA: tabby-wifi profili olusturulamadi" >&2
    return 1
  fi

  local hidden_flag=no
  case "${WIFI_HIDDEN:-}" in
    1|true|True|TRUE|yes|on) hidden_flag=yes ;;
  esac

  _run_maybe_timeout "$NMCLI_BIN" connection modify "$WIFI_CON_NAME" \
    connection.autoconnect yes \
    connection.autoconnect-retries -1 \
    connection.autoconnect-priority 50 \
    ipv4.route-metric 600 \
    802-11-wireless.hidden "$hidden_flag" \
    802-11-wireless.mac-address-randomization 0
}

_nmcli_con_prop() {
  local con_name="$1"
  local prop="$2"
  "$NMCLI_BIN" -g "$prop" connection show "$con_name" 2>/dev/null | head -1 || true
}

_bul_ethernet_profil() {
  local ifn="$1"
  local tabby_con="tabby-${ifn}"
  if "$NMCLI_BIN" connection show "$tabby_con" >/dev/null 2>&1; then
    echo "$tabby_con"
    return 0
  fi
  local name type iface active_name

  active_name="$("$NMCLI_BIN" -g GENERAL.CONNECTION device show "$ifn" 2>/dev/null | head -1 || true)"
  if [ -n "$active_name" ] && [ "$active_name" != "--" ]; then
    echo "$active_name"
    return 0
  fi

  while IFS= read -r name; do
    [ -z "$name" ] && continue
    type="$(_nmcli_con_prop "$name" connection.type)"
    [ "$type" = "802-3-ethernet" ] || continue
    iface="$(_nmcli_con_prop "$name" connection.interface-name)"
    if [ -z "$iface" ] || [ "$iface" = "--" ] || [ "$iface" = "$ifn" ]; then
      echo "$name"
      return 0
    fi
  done < <("$NMCLI_BIN" -t -f NAME connection show 2>/dev/null || true)

  return 1
}

_ethernet_profil_kur() {
  ETH_CON_NAME="tabby-${ETH_IF}"
  echo "Ethernet profili kuruluyor: ${ETH_CON_NAME} if=${ETH_IF} ip=${CIHAZ_IP:-dhcp}" >&2
  _run_maybe_timeout "$NMCLI_BIN" connection down "$ETH_CON_NAME"
  _run_maybe_timeout "$NMCLI_BIN" connection delete "$ETH_CON_NAME"

  local -a ekle_args=(
    type ethernet
    ifname "$ETH_IF"
    con-name "$ETH_CON_NAME"
    autoconnect yes
    connection.autoconnect yes
    connection.interface-name "$ETH_IF"
  )

  if [ -n "$CIHAZ_IP" ] && [ -n "$PREFIX" ]; then
    ekle_args+=(
      ipv4.method manual
      ipv4.addresses "${CIHAZ_IP}/${PREFIX}"
    )
    if [ -n "$GATEWAY" ]; then
      ekle_args+=(ipv4.gateway "$GATEWAY")
    fi
    if [ -n "$DNS" ]; then
      ekle_args+=(ipv4.dns "$DNS")
    fi
  else
    ekle_args+=(ipv4.method auto)
  fi

  if ! "$NMCLI_BIN" connection add "${ekle_args[@]}"; then
    echo "HATA: ${ETH_CON_NAME} profili olusturulamadi" >&2
    return 1
  fi

  _run_maybe_timeout "$NMCLI_BIN" connection modify "$ETH_CON_NAME" \
    connection.autoconnect-priority 100 \
    connection.interface-name "$ETH_IF" \
    ipv4.route-metric 100

  _run_maybe_timeout "$NMCLI_BIN" connection up "$ETH_CON_NAME" ifname "$ETH_IF"
}

_json_get() {
  local key="$1"
  python3 - "$CONFIG_JSON" "$key" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as f:
        j = json.load(f)
except Exception:
    print("")
    raise SystemExit(0)
v = j.get(key, "")
if isinstance(v, bool):
    print("1" if v else "0")
elif v is None:
    print("")
else:
    print(str(v))
PY
}

_mask_to_prefix() {
  python3 - "$1" <<'PY'
import sys
mask = (sys.argv[1] or "").strip()
parts = mask.split(".")
if len(parts) != 4:
    print("")
    raise SystemExit(0)
try:
    bits = "".join(f"{int(x):08b}" for x in parts)
except Exception:
    print("")
    raise SystemExit(0)
if "01" in bits:
    print("")
else:
    print(bits.count("1"))
PY
}

CIHAZ_ADI="$(_json_get cihaz_adi)"
CIHAZ_IP="$(_json_get cihaz_ip)"
SUBNET_MASK="$(_json_get subnet_mask)"
[ -z "$SUBNET_MASK" ] && SUBNET_MASK="$(_json_get subnet_musk)"
GATEWAY="$(_json_get gateway)"
DNS="$(_json_get dns)"
NTP_SERVER="$(_json_get ntp_server)"
WIFI_SSID="$(_json_get wifi_ssid)"
WIFI_PASSWORD="$(_json_get wifi_password)"
WIFI_HIDDEN="$(_json_get wifi_hidden)"
# TELETIP gibi gizli aglar icin: alan yoksa varsayilan gizli=true
if [ -z "$WIFI_HIDDEN" ] && [ -n "$WIFI_SSID" ]; then
  WIFI_HIDDEN="true"
fi
WIFI_IF="$(_json_get wifi_interface)"
ETH_IF="$(_json_get ethernet_interface)"
SERVIS_URL="$(_json_get servis_url)"
[ -z "$SERVIS_URL" ] && SERVIS_URL="$(_json_get kart_okuma_endpoint)"
SERVIS_TIMEOUT="$(_json_get servis_timeout_s)"
REBOOT_AFTER="$(_json_get reboot_after_apply)"
[ -z "$REBOOT_AFTER" ] && REBOOT_AFTER="0"
[ -z "$ETH_IF" ] && ETH_IF="eth0"
[ -z "$WIFI_IF" ] && WIFI_IF="wlan0"

python3 - "$DEVICE_INFO_JSON" "$CIHAZ_ADI" "$CIHAZ_IP" <<'PY'
import json, os, sys
path, name, ip = sys.argv[1], sys.argv[2], sys.argv[3]
cur = {}
if os.path.isfile(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        cur = {}
if name.strip():
    cur["cihaz_adi"] = name.strip()
if ip.strip():
    cur["cihaz_ip"] = ip.strip()
with open(path, "w", encoding="utf-8") as f:
    json.dump(cur, f, ensure_ascii=False, indent=2)
PY

python3 - "$APP_SETTINGS_JSON" "$SERVIS_URL" "$SERVIS_TIMEOUT" <<'PY'
import json, os, sys
path, servis_url, timeout_s = sys.argv[1], sys.argv[2], sys.argv[3]
cur = {}
if os.path.isfile(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        cur = {}
if servis_url.strip():
    cur["servis_url"] = servis_url.strip()
if timeout_s.strip():
    try:
        cur["servis_timeout_s"] = float(timeout_s.strip())
    except Exception:
        pass
with open(path, "w", encoding="utf-8") as f:
    json.dump(cur, f, ensure_ascii=False, indent=2)
PY

chown -R tabby:tabby "$CONFIG_DIR" "$(dirname "$CONFIG_JSON")" 2>/dev/null || true
if [ -f "$CONFIG_JSON" ] && [ "$CONFIG_JSON" != "$AYNA_CONFIG_JSON" ]; then
  mkdir -p "$CONFIG_DIR"
  cp "$CONFIG_JSON" "$AYNA_CONFIG_JSON"
  chown tabby:tabby "$AYNA_CONFIG_JSON" 2>/dev/null || true
fi

if [ -n "$NTP_SERVER" ]; then
  cat >/etc/systemd/timesyncd.conf <<EOF
[Time]
NTP=$NTP_SERVER
FallbackNTP=
EOF
  _run_maybe_timeout systemctl restart systemd-timesyncd
  _run_maybe_timeout timedatectl set-ntp true
fi

PREFIX="$(_mask_to_prefix "$SUBNET_MASK")"
if [ -z "$NMCLI_BIN" ]; then
  echo "nmcli bulunamadi; network/wifi ayarlari atlandi."
else
  _ethernet_profil_kur || echo "UYARI: ethernet profili kurulamadi" >&2
fi

if [ -n "$NMCLI_BIN" ] && [ -n "$WIFI_SSID" ]; then
  _wifi_profil_kur || true
fi

# Kiosk'ta baglanti istegi / NM bildirim pencerelerini engelle
if [ -x "${TABBY_ROOT}/scripts/kiosk_ui_engelle.sh" ]; then
  "${TABBY_ROOT}/scripts/kiosk_ui_engelle.sh" || true
fi

# Kalici servis/dispatcher/watch (her config apply'da tazelenir)
if [ -x "${TABBY_ROOT}/scripts/tabby_servisleri_kur.sh" ]; then
  "${TABBY_ROOT}/scripts/tabby_servisleri_kur.sh" || true
elif [ -x "${TABBY_ROOT}/scripts/tabby-nm-dispatcher.sh" ]; then
  install -m 0755 "${TABBY_ROOT}/scripts/tabby-nm-dispatcher.sh" \
    /etc/NetworkManager/dispatcher.d/99-tabby-failover
fi
if [ -x "${TABBY_ROOT}/scripts/tabby_network_failover.sh" ]; then
  TABBY_CONFIG_FILE="$CONFIG_JSON" TABBY_ETH_BEKLEME_S="${TABBY_ETH_BEKLEME_S:-15}" \
    "${TABBY_ROOT}/scripts/tabby_network_failover.sh" apply || true
fi

if [ "$REBOOT_AFTER" = "1" ] || [ "${REBOOT_AFTER,,}" = "true" ]; then
  python3 - "$CONFIG_JSON" "$AYNA_CONFIG_JSON" <<'PY'
import json, os, sys
paths = [p for p in sys.argv[1:] if p.strip()]
try:
    with open(paths[0], "r", encoding="utf-8") as f:
        j = json.load(f)
except Exception:
    j = {}
if isinstance(j, dict):
    j["reboot_after_apply"] = False
    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(j, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
PY
  _run_maybe_timeout /usr/sbin/reboot
fi
