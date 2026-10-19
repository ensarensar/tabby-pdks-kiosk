#!/bin/bash
# NetworkManager dispatcher — thrash etmeden eth/wifi olaylari.
IFACE="${1:-}"
ACTION="${2:-}"
SCRIPT="/home/tabby/tabby_kiosk/scripts/tabby_network_failover.sh"
[ -x "$SCRIPT" ] || exit 0
export TABBY_CONFIG_FILE="${TABBY_CONFIG_FILE:-/var/lib/tabby-kiosk/config.json}"

case "$IFACE" in
  eth0|en*)
    case "$ACTION" in
      up)
        logger -t tabby-failover "eth $IFACE $ACTION -> eth oncelik"
        "$SCRIPT" eth-up || true
        ;;
      down|pre-down)
        logger -t tabby-failover "eth $IFACE $ACTION -> wifi failover"
        "$SCRIPT" eth-down || true
        ;;
    esac
    ;;
  wlan*|wl*)
    case "$ACTION" in
      # connectivity-change cok sik tetiklenir — UP tekrarlama (telefon hotspot thrash)
      down|pre-down|failed)
        logger -t tabby-failover "wlan $IFACE $ACTION -> yeniden baglanma"
        "$SCRIPT" once || true
        ;;
    esac
    ;;
  *)
    exit 0
    ;;
esac
