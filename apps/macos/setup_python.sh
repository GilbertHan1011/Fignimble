#!/bin/bash
# Sets up the Python Fignimble's engine runs in, without Homebrew or an administrator password: a relocatable CPython
# (python-build-standalone, checked against its pinned SHA-256) with engine/requirements.txt installed into it, in
# ~/Library/Application Support/Fignimble/python. The app runs it from Contents/Resources when it finds no Python
# that can render; it also works on its own. Lines starting "@@ " are steps for the app's setup window.
set -euo pipefail

# the app says where it will look (FIGNIMBLE_SUPPORT), so the two always agree
SUPPORT="${FIGNIMBLE_SUPPORT:-$HOME/Library/Application Support/Fignimble}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# the requirements next to the engine: in the app (Contents/Resources/engine) or in a checkout (apps/macos -> engine)
REQ="$HERE/engine/requirements.txt"
[[ -f "$REQ" ]] || REQ="$HERE/../../engine/requirements.txt"
[[ -f "$REQ" ]] || { echo "Can't find engine/requirements.txt" >&2; exit 1; }

# the same build Manimble's runtime uses (apps/macos/tools/build_python_runtime.sh there); update the SHA-256s with it
PBS_TAG=20261021
PY_VERSION=3.11.17
if [[ "$(sysctl -n hw.optional.arm64 2>/dev/null)" == 1 ]]; then
  TRIPLE=aarch64-apple-darwin; PY_SHA256=1d1335d9d526bc37061af3fe72b0edd88056d7e7d9488eb631946b10b4ab97bb
else
  TRIPLE=x86_64-apple-darwin; PY_SHA256=2a9df73aa8f6ff595f912dfb642c7933f604f5c6e24234fd524cb77b2629b9fc
fi
URL="https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_TAG/cpython-$PY_VERSION+$PBS_TAG-$TRIPLE-install_only_stripped.tar.gz"

step() { echo "@@ $*"; }
# long steps run as children the shell waits on, so the setup window's Cancel (SIGTERM) stops them
trap 'pkill -P $$ 2>/dev/null; exit 143' TERM
run() { "$@" & wait $!; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

step "Downloading Python $PY_VERSION"
run curl -fL --retry 3 --progress-bar -o "$tmp/python.tar.gz" "$URL"
got="$(shasum -a 256 "$tmp/python.tar.gz" | cut -d' ' -f1)"
[[ "$got" == "$PY_SHA256" ]] || { echo "The Python download failed its checksum (expected $PY_SHA256, got $got)" >&2; exit 1; }

step "Unpacking Python"
run tar -xzf "$tmp/python.tar.gz" -C "$tmp"
PY="$tmp/python/bin/python3"
ln -sf python3 "$tmp/python/bin/python"

step "Installing matplotlib, PyMuPDF, Pillow, NumPy and BioCartoon"
run "$PY" -m pip install --disable-pip-version-check --no-warn-script-location --only-binary=:all: -r "$REQ"

step "Checking Python"
"$PY" -c "import matplotlib, pymupdf, PIL, numpy" || { echo "The new Python can't import what Fignimble needs" >&2; exit 1; }

mkdir -p "$SUPPORT"
# an earlier environment that no longer works (the app only sets up when it found none) is set aside, not deleted
if [[ -e "$SUPPORT/python" ]]; then
  rm -rf "$SUPPORT/python.previous"
  mv "$SUPPORT/python" "$SUPPORT/python.previous"
fi
mv "$tmp/python" "$SUPPORT/python"
# pip wrote the temporary folder into its scripts' first lines (bin/biocartoon, bin/pip...): point them at the
# Python where it is now, through /bin/sh, since "Application Support" has a space a #! line can't hold
"$SUPPORT/python/bin/python3" - "$(basename "$tmp")" "$SUPPORT/python/bin/python3" <<'PY'   # the temporary folder by its unique name (it may show as /var or /private/var)
import os, sys
old, new = sys.argv[1], sys.argv[2]
bindir = os.path.dirname(new)
for name in os.listdir(bindir):
    path = os.path.join(bindir, name)
    if os.path.islink(path) or not os.path.isfile(path):
        continue
    with open(path, "rb") as f:
        data = f.read()
    first, nl, rest = data.partition(b"\n")
    if first.startswith(b"#!") and old.encode() in first:
        shim = '#!/bin/sh\n\'\'\'exec\' "%s" "$0" "$@"\n\' \'\'\'\n' % new
        with open(path, "wb") as f:
            f.write(shim.encode() + rest)
PY
echo "Python installed at $SUPPORT/python"
