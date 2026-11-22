"""JSON lines over stdin/stdout, used by the Fignimble app (the protocol is Manimble's; see docs/protocol.md).

Request : {"id": 1, "cmd": "figure", ...args}
Response: {"id": 1, "result": {...}}  or  {"id": 1, "error": "..."}
Event   : {"event": "changed"}        (pushed, no id)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import templates
from .core import Session

_out = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
sys.stdout = sys.stderr
_wlock = threading.Lock()


def send(obj):
    line = json.dumps(obj)
    with _wlock:
        _out.write(line + "\n")


def main():
    python = os.environ.get("FIGNIMBLE_PYTHON") or sys.executable
    app = {"s": None}

    def need() -> Session:
        if app["s"] is None:
            raise RuntimeError("no project open")
        return app["s"]

    def open_project(a):
        old = app["s"]
        if old:
            old.close()
        s = Session(a["project"], python)
        s.on_event = send
        app["s"] = s
        return {"ok": True, "project": str(s.project)}

    def close(a):
        if app["s"]:
            app["s"].close()
            app["s"] = None
        return {"ok": True}

    handlers = {
        "open": open_project,
        "close": close,
        "new_project": lambda a: templates.new_project(a["dir"], a.get("journal")),
        "state": lambda a: need().api_state(),
        "figure": lambda a: need().api_figure(a),
        "edit": lambda a: need().edit(a),
        "write_source": lambda a: need().write_source(a),
        "undo": lambda a: need().undo(a),
        "undo_to": lambda a: need().undo_to(a),
        "copy": lambda a: need().copy(a),
        "paste": lambda a: need().paste(a),
        "paste_image": lambda a: need().paste_image(a),
        "redo": lambda a: need().redo_(a),
        "export": lambda a: need().export(a),
        "export_table": lambda a: need().export_table(a),
        "remote_hosts": lambda a: {"hosts": __import__("fignimble.remote", fromlist=["hosts"]).hosts()},
        "remote_list": lambda a: need().remote_list(a),
        "import_remote": lambda a: need().import_remote(a),
        "update_remote": lambda a: need().update_remote(a),
        "new_figure": lambda a: need().new_figure(a),
        "new_panel": lambda a: need().new_panel(a),
        "import_file": lambda a: need().import_file(a),
        # in their order (by publisher), which a JSON object doesn't keep for the app
        "journals": lambda a: {k: {**j, "rank": i} for i, (k, j) in
                               enumerate(__import__("fignimble.journals", fromlist=["JOURNALS"]).JOURNALS.items())},
    }
    pool = ThreadPoolExecutor(max_workers=6)

    def run(req):
        try:
            res = handlers[req["cmd"]](req)
            send({"id": req["id"], "result": res})
        except BaseException as exc:  # noqa: BLE001
            traceback.print_exc()
            send({"id": req.get("id"), "error": str(exc)})

    for line in sys.stdin:
        line = line.strip()
        if line:
            req = json.loads(line)
            if req.get("cmd") in ("open", "close"):     # order matters: finish before later requests
                run(req)
            else:
                pool.submit(run, req)
    if app["s"]:
        app["s"].close()


if __name__ == "__main__":
    main()
