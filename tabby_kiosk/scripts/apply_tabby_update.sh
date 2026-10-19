#!/bin/bash
# Tabby kiosk uygulama guncellemesi: bundle indir, dogrula, kur, servisleri yeniden baslat.
# OTA sirasinda LCD overlay / config.txt'e dokunulmaz.
set -euo pipefail

BUNDLE_URL="${1:-}"
VERSION="${2:-}"
EXPECTED_SHA256="${3:-}"
INSTALL_DIR="${TABBY_INSTALL_DIR:-/home/tabby/tabby_kiosk}"
UPDATE_ROOT="${TABBY_UPDATE_DIR:-/var/lib/tabby-kiosk/updates}"
STAGING="${UPDATE_ROOT}/staging"
ARCHIVE="${UPDATE_ROOT}/bundle.tar.gz"
BACKUP="${UPDATE_ROOT}/backup"
LOCK="${UPDATE_ROOT}/apply.lock"
LOG_TAG="[tabby-update]"
CURL_INSECURE="${TABBY_CURL_INSECURE:-1}"

_log() {
  echo "${LOG_TAG} $*" >&2
}

_fail() {
  _log "HATA: $*"
  exit 1
}

[ -n "$BUNDLE_URL" ] || _fail "bundle_url bos"
[ -n "$VERSION" ] || _fail "version bos"
[ -n "$EXPECTED_SHA256" ] || _fail "sha256 bos"

mkdir -p "$UPDATE_ROOT" "$(dirname "$INSTALL_DIR")"
chmod 755 "$UPDATE_ROOT" 2>/dev/null || true

exec 9>"$LOCK"
if ! flock -n 9; then
  _log "baska guncelleme calisiyor"
  printf '{"ok":true,"busy":true,"version":"%s"}\n' "$VERSION"
  exit 0
fi

MEVCUT=""
if [ -f "$INSTALL_DIR/VERSION" ]; then
  MEVCUT="$(tr -d '[:space:]' < "$INSTALL_DIR/VERSION" || true)"
fi
if [ -n "$MEVCUT" ] && [ "$MEVCUT" = "$VERSION" ]; then
  _log "zaten v${VERSION}"
  printf '{"ok":true,"version":"%s","skipped":true}\n' "$VERSION"
  exit 0
fi

_log "Indiriliyor: $BUNDLE_URL"
if command -v curl >/dev/null 2>&1; then
  CURL_OPTS=(-fsSL --connect-timeout 20 --max-time 600)
  if [ "$CURL_INSECURE" = "1" ]; then
    CURL_OPTS+=(-k)
  fi
  curl "${CURL_OPTS[@]}" "$BUNDLE_URL" -o "$ARCHIVE"
elif command -v wget >/dev/null 2>&1; then
  WGET_OPTS=(-q -O "$ARCHIVE")
  if [ "$CURL_INSECURE" = "1" ]; then
    WGET_OPTS+=(--no-check-certificate)
  fi
  wget "${WGET_OPTS[@]}" "$BUNDLE_URL"
else
  _fail "curl veya wget bulunamadi"
fi

ACTUAL_SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')"
EXPECTED_SHA256_LC="$(echo "$EXPECTED_SHA256" | tr '[:upper:]' '[:lower:]')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256_LC" ]; then
  _fail "sha256 uyusmuyor (beklenen=${EXPECTED_SHA256} gercek=${ACTUAL_SHA256})"
fi
_log "sha256 dogrulandi"

rm -rf "$STAGING"
mkdir -p "$STAGING"
tar -xzf "$ARCHIVE" -C "$STAGING"

SRC="$STAGING"
if [ -d "$STAGING/tabby_kiosk" ]; then
  SRC="$STAGING/tabby_kiosk"
fi
if [ ! -f "$SRC/main.py" ]; then
  _fail "paket gecersiz: main.py bulunamadi"
fi

_log "Kurulum dizini: $INSTALL_DIR"
if [ -d "$INSTALL_DIR" ]; then
  rm -rf "$BACKUP"
  cp -a "$INSTALL_DIR" "$BACKUP"
  _log "Yedek alindi: $BACKUP"
fi

mkdir -p "$INSTALL_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    "$SRC/" "$INSTALL_DIR/"
else
  cp -a "$SRC/." "$INSTALL_DIR/"
fi

if [ -d "$INSTALL_DIR/scripts" ]; then
  chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true
fi

echo "$VERSION" > "$INSTALL_DIR/VERSION"
chown -R tabby:tabby "$INSTALL_DIR" 2>/dev/null || true

# Overlay/config.txt'e dokunma (beyaz LCD riski). Servisleri gecikmeli restart
# ki bu surec (config-agent/kiosk) kendini yarıda oldurmesin.
_log "Servisler 2s sonra yeniden baslatilacak"
RESTART_CMD='systemctl try-restart tabby-kiosk.service tabby-kiosk-popup-bekci.service tabby-config-agent.service'
systemctl stop tabby-ota-restart.service 2>/dev/null || true
systemctl reset-failed tabby-ota-restart.service 2>/dev/null || true
if command -v systemd-run >/dev/null 2>&1 \
  && systemd-run --quiet --collect --on-active=2s --unit=tabby-ota-restart.service \
    /bin/bash -c "$RESTART_CMD" >/dev/null 2>&1; then
  _log "restart zamanlandi (systemd-run)"
else
  nohup bash -c "sleep 2; $RESTART_CMD" >/dev/null 2>&1 &
  _log "restart zamanlandi (nohup)"
fi

_log "Guncelleme tamamlandi: v${VERSION}"
printf '{"ok":true,"version":"%s","install_dir":"%s"}\n' "$VERSION" "$INSTALL_DIR"
