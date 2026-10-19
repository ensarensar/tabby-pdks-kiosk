#!/bin/bash
# Gelistirme makinesinde kiosk paketini olusturur.
set -euo pipefail

TABBY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${TABBY_ROOT}/VERSION")"
[ -n "$VERSION" ] || VERSION="0.0.0"
OUT_DIR="${1:-${TABBY_ROOT}/dist}"
ARCHIVE="${OUT_DIR}/tabby-kiosk-${VERSION}.tar.gz"

mkdir -p "$OUT_DIR"
tar -czf "$ARCHIVE" \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  --exclude 'dist' \
  -C "$(dirname "$TABBY_ROOT")" "$(basename "$TABBY_ROOT")"

SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
echo "Paket: $ARCHIVE"
echo "Surum: $VERSION"
echo "SHA256: $SHA256"
