#!/usr/bin/env python3
"""Stage the Fignimble GeWu plugin with a pinned SDK, engine and interpreter.

This is a development/local install: the launcher binds one Python that has
Fignimble's dependencies. A marketplace release uses the host's runtime plan
instead (`build-release.py`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

FILES = ("plugin.json", "adapter.py", "engine_client.py", "tools.schema.json", "probe.py",
         "README.md", "INSTALL.md")
DIRS = ("bin", "web", "skills")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(sdk_root: Path, python: Path, out: Path, engine_root: Path, repo: Path) -> None:
    here = Path(__file__).resolve().parent
    out = out.absolute()
    if out.exists() or out.is_symlink():
        raise ValueError(f"choose a new staging directory: {out}")
    if not (engine_root / "fignimble" / "rpc.py").is_file():
        raise ValueError(f"no Fignimble engine at {engine_root}")
    if not (sdk_root / "gewu_plugin.py").is_file():
        raise ValueError(f"no GeWu SDK at {sdk_root}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        stage_dir = Path(temp) / "package"
        stage_dir.mkdir()
        for name in FILES:
            shutil.copy2(here / name, stage_dir / name)
        for name in DIRS:
            shutil.copytree(here / name, stage_dir / name)
        (stage_dir / "lib").mkdir()
        shutil.copy2(sdk_root / "gewu_plugin.py", stage_dir / "lib/gewu_plugin.py")
        engine_dir = stage_dir / "engine"
        engine_dir.mkdir()
        shutil.copytree(engine_root / "fignimble", engine_dir / "fignimble",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(engine_root / "requirements.txt", engine_dir / "requirements.txt")
        version = (repo / "VERSION")
        if version.is_file():
            shutil.copy2(version, stage_dir / "VERSION")
        launcher = stage_dir / "bin" / "fignimble-gewu"
        launcher.write_text(launcher.read_text().replace("@PYTHON@", str(python)))
        launcher.chmod(0o755)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        hashes = {name: sha256(stage_dir / name) for name in
                  ("plugin.json", "adapter.py", "engine_client.py", "tools.schema.json")}
        (stage_dir / "compatibility.json").write_text(json.dumps({
            "apiVersion": "gewu.plugin/v1", "plugin": "fignimble", "sourceCommit": commit,
            "requires": ["Python 3.11+", "matplotlib", "PyMuPDF<2", "Pillow", "NumPy"],
            "files": hashes, "python": python.name,
        }, indent=2) + "\n")
        stage_dir.rename(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--engine-root", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    engine_root = args.engine_root or (repo / "engine")
    try:
        stage(args.sdk_root, args.python.absolute(), args.out, engine_root.resolve(), repo)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(json.dumps({"package": str(args.out.absolute())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
