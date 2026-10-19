#!/bin/bash
# Ethernet oncelikli failover + WiFi yeniden baglanma (sakin / thrash yok).
# - Eth bagliyken WiFi DOWN (LAN oncelik) — beklenen
# - Eth dusunce WiFi UP
# - WiFi zaten bagli/ baglaniyorsa TEKRAR UP ATMA (telefon hotspot thrash engeli)
set -uo pipefail

TABBY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TABBY_HOME="${TABBY_HOME:-/home/tabby}"
CONFIG_JSON="${TABBY_CONFIG_FILE:-/var/lib/tabby-kiosk/config.json}"
[ -f "$CONFIG_JSON" ] || CONFIG_JSON="${TABBY_HOME}/.config/tabby-kiosk/config.json"
STATUS_FILE="${TABBY_FAILOVER_STATUS_FILE:-/var/lib/tabby-kiosk/failover.status}"
LOG_FILE="${TABBY_FAILOVER_LOG_FILE:-/var/lib/tabby-kiosk/failover.log}"

NMCLI_BIN="$(command -v nmcli || true)"
WAIT_S="${TABBY_ETH_BEKLEME_S:-10}"
ARALIK_S="${TABBY_FAILOVER_ARALIK_S:-8}"
WIFI_RETRY_S="${TABBY_WIFI_RETRY_S:-30}"
WIFI_CON_NAME="tabby-wifi"
FORCE_WIFI="${TABBY_FORCE_WIFI:-0}"
_SON_WIFI_DENEME_TS=0

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

ETH_IF="$(_json_get ethernet_interface)"
WIFI_IF="$(_json_get wifi_interface)"
[ -z "$ETH_IF" ] && ETH_IF="eth0"
[ -z "$WIFI_IF" ] && WIFI_IF="wlan0"

_log() {
  local msg="$*"
  local line="[tabby-failover] $(date '+%F %H:%M:%S') $msg"
  echo "$line" >&2
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
  echo "$line" >> "$LOG_FILE" 2>/dev/null || true
  logger -t tabby-failover -- "$msg" 2>/dev/null || true
}

_status_yaz() {
  local tip="$1"
  local detay="${2:-}"
  mkdir -p "$(dirname "$STATUS_FILE")" 2>/dev/null || true
  printf '%s\n%s\n%s\n' "$tip" "$detay" "$(date -Iseconds)" > "$STATUS_FILE" 2>/dev/null || true
}

_now_ts() { date +%s; }

_eth_carrier_var_mi() {
  [ -f "/sys/class/net/${ETH_IF}/carrier" ] && [ "$(cat "/sys/class/net/${ETH_IF}/carrier" 2>/dev/null || echo 0)" = "1" ]
}

_eth_ip_var_mi() {
  ip -4 -o addr show dev "$ETH_IF" 2>/dev/null | grep -q " inet "
}

_eth_bagli_mi() {
  _eth_carrier_var_mi && _eth_ip_var_mi
}

_wifi_ip_var_mi() {
  ip -4 -o addr show dev "$WIFI_IF" 2>/dev/null | grep -q " inet "
}

_wifi_nm_state() {
  "$NMCLI_BIN" -g GENERAL.STATE device show "$WIFI_IF" 2>/dev/null || echo ""
}

_wifi_bagli_mi() {
  # IP varsa yeter (state gecici 70/80 olsa bile thrash etme)
  _wifi_ip_var_mi && return 0
  local st
  st="$(_wifi_nm_state)"
  echo "$st" | grep -qiE '100 \(connected\)' || return 1
  return 0
}

_wifi_mesgul_mu() {
  # Baglaniyor / IP aliyor — tekrar UP atma
  local st
  st="$(_wifi_nm_state)"
  echo "$st" | grep -qiE '\(connecting|prepare|config|ip-config|ip-check|secondaries|activated|need-auth\)' && return 0
  echo "$st" | grep -qiE '^[0-9]+ \(connected\)' && return 0
  return 1
}

_wifi_profil_var_mi() {
  [ -n "$NMCLI_BIN" ] && "$NMCLI_BIN" connection show "$WIFI_CON_NAME" >/dev/null 2>&1
}

_bul_ethernet_profil() {
  local tabby_con="tabby-${ETH_IF}"
  if "$NMCLI_BIN" connection show "$tabby_con" >/dev/null 2>&1; then
    echo "$tabby_con"
    return 0
  fi
  local active
  active="$("$NMCLI_BIN" -g GENERAL.CONNECTION device show "$ETH_IF" 2>/dev/null | head -1 || true)"
  if [ -n "$active" ] && [ "$active" != "--" ]; then
    echo "$active"
    return 0
  fi
  echo "$tabby_con"
}

_ethernet_ac() {
  local con="$1"
  _log "Ethernet UP: $con ($ETH_IF)"
  "$NMCLI_BIN" -w 15 connection up "$con" >/dev/null 2>&1 || true
}

_wifi_kapat() {
  _log "WiFi DOWN: $WIFI_CON_NAME (ethernet oncelikli)"
  "$NMCLI_BIN" -w 8 connection down "$WIFI_CON_NAME" >/dev/null 2>&1 || true
}

_eth_stale_ip_temizle() {
  if ! _eth_carrier_var_mi; then
    if _eth_ip_var_mi; then
      _log "Ethernet stale IP flush ($ETH_IF)"
      ip -4 addr flush dev "$ETH_IF" 2>/dev/null || true
    fi
    while ip route show default 2>/dev/null | grep -q "dev ${ETH_IF}"; do
      ip route del default dev "$ETH_IF" 2>/dev/null || break
    done
    local eth_con
    eth_con="$(_bul_ethernet_profil)"
    "$NMCLI_BIN" -w 5 connection down "$eth_con" >/dev/null 2>&1 || true
  fi
}

_wifi_profil_ssid_uyumsuz_mu() {
  local hedef mevcut
  hedef="$(_json_get wifi_ssid)"
  [ -z "$hedef" ] && hedef="TELETIP"
  mevcut="$("$NMCLI_BIN" -g 802-11-wireless.ssid connection show "$WIFI_CON_NAME" 2>/dev/null | head -1 || true)"
  [ "$mevcut" != "$hedef" ]
}

_wifi_profil_hazirla() {
  local ssid password hidden force_rebuild="${1:-0}"
  ssid="$(_json_get wifi_ssid)"
  password="$(_json_get wifi_password)"
  hidden="$(_json_get wifi_hidden)"
  [ -z "$ssid" ] && ssid="TELETIP"
  if [ -z "$hidden" ] || [ "$hidden" = "1" ] || [ "${hidden,,}" = "true" ]; then
    hidden="yes"
  else
    hidden="no"
  fi

  local rebuild=0
  if [ "$force_rebuild" = "1" ]; then
    rebuild=1
  elif ! _wifi_profil_var_mi; then
    rebuild=1
  elif _wifi_profil_ssid_uyumsuz_mu; then
    _log "WiFi SSID degisti ($ssid) — profil yenilenecek"
    rebuild=1
  fi

  if [ "$rebuild" != "1" ]; then
    # Bagliyken connection modify YAPMA — thrash eder
    return 0
  fi

  if _wifi_profil_var_mi; then
    _log "WiFi profili siliniyor (yeniden kurulum)"
    "$NMCLI_BIN" -w 5 connection delete "$WIFI_CON_NAME" >/dev/null 2>&1 || true
  fi
  _log "WiFi profili olusturuluyor ssid=$ssid hidden=$hidden password=$([ -n "$password" ] && echo set || echo empty)"
  local -a add_args=(
    type wifi ifname "$WIFI_IF" con-name "$WIFI_CON_NAME" ssid "$ssid"
    autoconnect yes
    ipv4.method auto
    ipv6.method ignore
    802-11-wireless.mode infrastructure
    802-11-wireless.hidden "$hidden"
    802-11-wireless.mac-address-randomization 0
    connection.autoconnect-retries -1
    connection.autoconnect-priority 50
    ipv4.route-metric 600
  )
  if [ -n "$password" ]; then
    add_args+=(wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$password")
  fi
  if ! "$NMCLI_BIN" connection add "${add_args[@]}" >>"$LOG_FILE" 2>&1; then
    _log "HATA: tabby-wifi olusturulamadi"
    return 1
  fi
  return 0
}

_wifi_ac() {
  local ssid st out Rc now
  ssid="$(_json_get wifi_ssid)"
  [ -z "$ssid" ] && ssid="TELETIP"

  # Zaten bagli veya baglaniyor → dokunma
  if _wifi_bagli_mi; then
    local ipw
    ipw="$(ip -4 -o addr show dev "$WIFI_IF" 2>/dev/null | awk '{print $4}' | head -1)"
    _status_yaz "wifi_ok" "ip=$ipw"
    return 0
  fi
  if _wifi_mesgul_mu; then
    _log "WiFi mesgul ($(_wifi_nm_state)) — UP atlanıyor"
    _status_yaz "wifi_trying" "busy"
    return 0
  fi

  # Basarisiz deneme backoff (watch thrash engeli)
  now="$(_now_ts)"
  if [ "$_SON_WIFI_DENEME_TS" -gt 0 ]; then
    local gecen=$((now - _SON_WIFI_DENEME_TS))
    if [ "$gecen" -lt "$WIFI_RETRY_S" ]; then
      _log "WiFi retry bekleniyor (${gecen}/${WIFI_RETRY_S}s)"
      return 1
    fi
  fi
  _SON_WIFI_DENEME_TS="$now"

  _status_yaz "wifi_trying" "ssid=$ssid"
  if ! _wifi_profil_hazirla 0; then
    _status_yaz "wifi_fail" "profil yok"
    return 1
  fi

  if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock wifi 2>/dev/null || true
  fi
  "$NMCLI_BIN" radio wifi on >/dev/null 2>&1 || true
  "$NMCLI_BIN" device set "$WIFI_IF" managed yes >/dev/null 2>&1 || true
  "$NMCLI_BIN" device set "$WIFI_IF" autoconnect yes >/dev/null 2>&1 || true
  ip link set "$WIFI_IF" up 2>/dev/null || true

  st="$(_wifi_nm_state)"
  _log "WiFi once durum=$st"
  _log ">>> RF/NM BAGLANTI ISTEGI: nmcli -w 45 connection up $WIFI_CON_NAME ssid=$ssid"
  out="$("$NMCLI_BIN" -w 45 connection up "$WIFI_CON_NAME" 2>&1)" && Rc=0 || Rc=$?
  _log "<<< nmcli UP rc=$Rc cikti: ${out:-<bos>}"

  # Secrets hatasi + acik ag bekleniyorsa profil rebuild (WPA doluyken degil)
  if [ "$Rc" -ne 0 ] && echo "$out" | grep -qiE 'secret|wep-key|passwords? or encryption'; then
    local pw
    pw="$(_json_get wifi_password)"
    if [ -z "$pw" ]; then
      _log "Secrets/WEP (acik ag) — profil yeniden kuruluyor"
      _wifi_profil_hazirla 1 || true
      out="$("$NMCLI_BIN" -w 45 connection up "$WIFI_CON_NAME" 2>&1)" && Rc=0 || Rc=$?
      _log "<<< nmcli UP(rebuild) rc=$Rc cikti: ${out:-<bos>}"
    fi
  fi

  # Radio cycle SADECE ilk UP tamamen failed + cihaz disconnected ise
  if [ "$Rc" -ne 0 ] && ! _wifi_bagli_mi && ! _wifi_mesgul_mu; then
    _log "UP basarisiz — tek radio cycle"
    "$NMCLI_BIN" radio wifi off >/dev/null 2>&1 || true
    sleep 2
    "$NMCLI_BIN" radio wifi on >/dev/null 2>&1 || true
    sleep 3
    out="$("$NMCLI_BIN" -w 45 connection up "$WIFI_CON_NAME" 2>&1)" && Rc=0 || Rc=$?
    _log "<<< nmcli UP(2) rc=$Rc cikti: ${out:-<bos>}"
  fi

  sleep 2
  if _wifi_bagli_mi; then
    local ipw
    ipw="$(ip -4 -o addr show dev "$WIFI_IF" 2>/dev/null | awk '{print $4}' | head -1)"
    _log "WiFi BAGLANDI ip=$ipw"
    _status_yaz "wifi_ok" "ip=$ipw"
    _SON_WIFI_DENEME_TS=0
    return 0
  fi

  st="$(_wifi_nm_state)"
  _log "WiFi BAGLANAMADI durum=$st — ${WIFI_RETRY_S}s backoff"
  _status_yaz "wifi_fail" "rc=$Rc state=$st"
  return 1
}

_ethernet_oncelikli() {
  local eth_con="$(_bul_ethernet_profil)"
  _status_yaz "eth_trying" "$eth_con"
  _ethernet_ac "$eth_con"
  local i=1
  while [ "$i" -le "$WAIT_S" ]; do
    if _eth_bagli_mi; then
      _log "Ethernet hazir — WiFi kapatilacak"
      _status_yaz "eth_ok" "ip=$(ip -4 -o addr show dev "$ETH_IF" 2>/dev/null | awk '{print $4}' | head -1)"
      _wifi_kapat
      return 0
    fi
    if ! _eth_carrier_var_mi; then
      break
    fi
    sleep 1
    i=$((i + 1))
  done
  _log "Ethernet hazir olmadi — WiFi deneniyor"
  _wifi_ac || true
}

_eth_geldi_wifi_kapat() {
  local eth_con="$(_bul_ethernet_profil)"
  if ! _eth_carrier_var_mi; then
    return 0
  fi
  _ethernet_ac "$eth_con"
  local i=1
  while [ "$i" -le 5 ]; do
    if _eth_bagli_mi; then
      _wifi_kapat
      _status_yaz "eth_ok" ""
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
}

_eth_dustu_wifi_zorla() {
  _log "Ethernet DUSTU — WiFi failover zorla"
  _SON_WIFI_DENEME_TS=0
  _status_yaz "wifi_trying" "eth-down"
  _eth_stale_ip_temizle
  _wifi_ac || true
}

_ag_dongusu() {
  _eth_stale_ip_temizle

  if [ "$FORCE_WIFI" = "1" ]; then
    _log "TABBY_FORCE_WIFI=1 — ethernet atlanıyor, WiFi zorunlu"
    _SON_WIFI_DENEME_TS=0
    _wifi_ac || true
    return 0
  fi

  if _eth_bagli_mi; then
    local eip
    eip="$(ip -4 -o addr show dev "$ETH_IF" 2>/dev/null | awk '{print $4}' | head -1)"
    # Sessiz status — log spam yok
    _status_yaz "eth_ok" "ip=$eip"
    if _wifi_bagli_mi || _wifi_ip_var_mi; then
      _eth_geldi_wifi_kapat
    fi
    return 0
  fi

  if _eth_carrier_var_mi; then
    # Kablo var IP yok: eth dene ama WiFi'yi oldurme (evde bos kablo thrash)
    if _wifi_bagli_mi; then
      local wip
      wip="$(ip -4 -o addr show dev "$WIFI_IF" 2>/dev/null | awk '{print $4}' | head -1)"
      _status_yaz "wifi_ok" "ip=$wip eth-link-no-ip"
      return 0
    fi
    _log "Dongu: Ethernet kablo var ama IP yok — eth sonra wifi"
    _ethernet_oncelikli
    return 0
  fi

  if _wifi_bagli_mi; then
    local wip
    wip="$(ip -4 -o addr show dev "$WIFI_IF" 2>/dev/null | awk '{print $4}' | head -1)"
    _status_yaz "wifi_ok" "ip=$wip"
    return 0
  fi

  _log "Dongu: Ethernet YOK — WiFi UP (gerekirse)"
  _wifi_ac || true
}

_mod="${1:-boot}"

if [ -z "$NMCLI_BIN" ]; then
  _log "nmcli yok"
  exit 0
fi

mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

case "$_mod" in
  boot|apply|once|wifi-up|wifi-down)
    _ag_dongusu
    ;;
  eth-up)
    _eth_geldi_wifi_kapat
    ;;
  eth-down)
    _eth_dustu_wifi_zorla
    ;;
  force-wifi)
    FORCE_WIFI=1
    _ag_dongusu
    ;;
  watch)
    _log "Watch basladi aralik=${ARALIK_S}s retry=${WIFI_RETRY_S}s log=$LOG_FILE"
    _onceki_eth=0
    _eth_bagli_mi && _onceki_eth=1 || true
    while true; do
      _simdi_eth=0
      _eth_bagli_mi && _simdi_eth=1 || true
      if [ "$_onceki_eth" = "1" ] && [ "$_simdi_eth" = "0" ]; then
        _log "Watch: ethernet ONLINE→OFFLINE"
        _eth_dustu_wifi_zorla
      else
        _ag_dongusu || true
      fi
      _onceki_eth="$_simdi_eth"
      sleep "$ARALIK_S"
    done
    ;;
  *)
    _log "Bilinmeyen mod: $_mod"
    exit 1
    ;;
esac
