#!/bin/bash
# Package Fignimble.app as a drag-to-Applications disk image.
#
#   apps/macos/make_dmg.sh [app] [out.dmg]    (defaults: apps/macos/Fignimble.app, apps/macos/.build/Fignimble-macOS.dmg)
#
# The image is signed when FIGNIMBLE_SIGN_IDENTITY is a Developer ID; notarizing it is up to the caller (release.yml).
# Python is not inside: the app needs a Python 3.10+ with matplotlib, PyMuPDF and Pillow (see the README).
set -euo pipefail
# relative arguments are relative to where the script was run from, not to this folder
abs() { [[ "$1" == /* ]] && echo "$1" || echo "$PWD/$1"; }
APP_ARG="${1:+$(abs "$1")}"
OUT_ARG="${2:+$(abs "$2")}"
cd "$(dirname "$0")"
ROOT="$PWD"
APP="${APP_ARG:-$ROOT/Fignimble.app}"
OUT="${OUT_ARG:-$ROOT/.build/Fignimble-macOS.dmg}"
mkdir -p "$(dirname "$OUT")"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/Fignimble.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname Fignimble -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$OUT"

SIGN_ID="${FIGNIMBLE_SIGN_IDENTITY:-}"
if [[ "$SIGN_ID" == "Developer ID Application"* ]]; then
  codesign -s "$SIGN_ID" --timestamp "$OUT"
fi
echo "built $OUT ($(du -h "$OUT" | cut -f1))"
