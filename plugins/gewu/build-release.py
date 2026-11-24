#!/usr/bin/env python3
"""Build the Fignimble plugin package (and optionally a marketplace release record).

The package is assembled from this checkout by GeWu's own `plugin-release.py`,
with the engine and VERSION added. A marketplace record uses the runtime plan
(external or host-managed Python), so no interpreter path is baked in.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def run(argv):
    subprocess.run([str(item) for item in argv], check=True)
    return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gewu-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version", default=json.loads((HERE / "release.json").read_text())["version"])
    parser.add_argument("--base-url", help="public base URL, needed for a marketplace record")
    parser.add_argument("--marketplace-root", type=Path, help="gewu-marketplace checkout")
    parser.add_argument("--host-version", default="v0.1.11")
    parser.add_argument("--created-at", default="")
    parser.add_argument("--channel", default="stable")
    args = parser.parse_args()
    out = args.out.absolute()
    if out.exists():
        parser.error(f"choose a new output directory: {out}")
    for base in (REPO / "engine", HERE):
        for cache in base.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        for bytecode in base.rglob("*.pyc"):
            bytecode.unlink(missing_ok=True)
    descriptor = json.loads((HERE / "release.json").read_text())
    descriptor["version"] = args.version
    temp_descriptor = out.parent / f".fignimble-release-{args.version}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    temp_descriptor.write_text(json.dumps(descriptor, indent=2) + "\n")
    try:
        run([sys.executable, args.gewu_root / "scripts/plugin-release.py",
             "--descriptor", temp_descriptor, "--source-root", HERE,
             "--sdk-root", args.gewu_root / "sdk/python", "--out", out / "package",
             "--allow-dirty",
             "--add-dir", f"engine={REPO / 'engine'}",
             "--add-file", f"VERSION={REPO / 'VERSION'}",
             "--add-file", f"engine/requirements.txt={REPO / 'engine/requirements.txt'}"])
    finally:
        temp_descriptor.unlink(missing_ok=True)
    packages = sorted((out / "package").glob("*.package.json"))
    if len(packages) != 1:
        parser.error("plugin-release.py did not write one package record")
    result = {"package": str(out / "package"), "record": str(packages[0])}
    if args.marketplace_root:
        if not args.base_url:
            parser.error("--base-url is required with --marketplace-root")
        run([sys.executable, args.marketplace_root / "publisher/make_release.py",
             "--package", packages[0], "--runtime-plan", HERE / "runtime-plan.json",
             "--host-version", args.host_version, "--base-url", args.base_url,
             "--source", f"fignimble@{REPO.name}", "--created-at", args.created_at,
             "--channel", args.channel, "--notes", f"Fignimble {args.version} figure editor in GeWu",
             "--out", out / "release.json"])
        result["release"] = json.loads((out / "release.json").read_text())
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
