"""
Local test frontend for the plan analysis (prototype).

    python3 src/app.py                -> opens http://127.0.0.1:8765 in the browser
    python3 src/app.py --no-browser   -> only starts the server
    python3 src/app.py --port 8766    -> other port (e.g. second instance)

Open a folder -> saved results are shown at once, only new or changed
plans are analysed (scan_plan_htw_api_v10) in the background. On start the
last folder is opened again. "Re-analyse all" analyses every plan again and
overwrites the model's values (reviews are kept).
Click an entry to see the plan in original resolution, correct location
and title and set the traffic light (human in the loop).

All data (results, reviews, exports, image cache) is stored in the project
under data/ (see store.py) - the plan folder is only read.

Only binds to 127.0.0.1: the app is not reachable from other computers.
"""

import errno
import io
import json
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import scan_plan_htw_api_v10 as scan
import store
from export_xlsx import write_xlsx
from models import FIELDS, ImageData, Review, TrafficLight
from search import search


HOST = "127.0.0.1"
PORT = 8765

INDEX_HTML = Path(__file__).parent / "static" / "index.html"

# Bump when the JSON sent to the page changes. The page reloads
# index.html on every request, so a server started with older code
# would otherwise silently serve data the page cannot read.
API_VERSION = 10


# Native folder dialog in its own process: tkinter must run on the
# main thread (macOS), the web server handles requests in threads.
PICK_FOLDER_SCRIPT = """
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
print(filedialog.askdirectory(title="Choose the folder with plans") or "")
"""


# ------------------------------------------------------------
# State of the current analysis
# ------------------------------------------------------------

class Job:

    def __init__(self):
        self.lock = threading.Lock()
        self.folder: Path | None = None
        self.running = False
        self.done = 0
        self.total = 0
        self.entries: dict[str, ImageData] = {}
        self.reviews: dict[str, Review] = {}
        self.error: str | None = None
        self.xlsx: str | None = None
        self.seconds: float | None = None
        self.mode = "new"          # "new": only new / changed plans, "all": everything
        self.loaded = 0            # plans shown from saved results when the folder was opened
        self.pending = 0           # plans to analyse in this run
        self.notes: list[str] = [] # data imported from the plan folder (v8 / v9)


job = Job()


def entry_payload(e: ImageData) -> dict:
    data = e.model_dump(mode="json")
    data["overall_level"] = e.overall_level.value if e.overall_level else None
    data["filename_flags"] = e.filename_flags
    data["review_status"] = e.review_status
    # what the list shows: reviewed value / traffic light if corrected
    data["values"] = {f: e.value(f) for f in FIELDS}
    data["levels"] = {f: (e.level(f).value if e.level(f) else None) for f in FIELDS}
    return data


def clean_text(value) -> str:
    return " ".join(str(value or "").split())


def build_review(e: ImageData, data: dict) -> Review:
    """
    Review from the popup form. The confirmed / corrected values are
    stored as they are ("" = not on the plan), so a new analysis cannot
    change what a human has checked.
    """

    values = {f: clean_text(data.get(f)) for f in FIELDS}

    levels = {
        f"{f}_level": TrafficLight(data[f"{f}_level"]) if data.get(f"{f}_level") else None
        for f in FIELDS
    }

    return Review(
        **values,
        **levels,
        reviewed_at=datetime.now().isoformat(timespec="seconds")
    )


def store_review(filename: str, review: Review | None) -> tuple[int, dict]:
    """Save (or with None: remove) the review of one plan."""

    with job.lock:

        e = job.entries.get(filename)

        if e is None or job.folder is None:
            return 404, {"error": "Plan not found"}

        e.review = review

        if review is None:
            job.reviews.pop(filename, None)
        else:
            job.reviews[filename] = review

        scan.save_reviews(job.folder, job.reviews)

        # Keep the Excel file up to date
        # (during an analysis it is written at the end)
        if not job.running:
            scan.write_entries(job.folder, list(job.entries.values()), job.seconds)

        return 200, entry_payload(e)


def state_payload() -> dict:
    with job.lock:
        script = Path(scan.__file__).name
        return {
            "api": API_VERSION,
            "folder": str(job.folder) if job.folder else None,
            "data_dir": str(store.folder_dir(job.folder)) if job.folder else None,
            "mode": job.mode,
            "loaded": job.loaded,
            "pending": job.pending,
            "notes": job.notes,
            # analysed with an older script version (only "Re-analyse all" updates them)
            "outdated": sum(
                1 for e in job.entries.values()
                if e.analysis is None or e.analysis.script != script
            ),
            "script": script,
            "running": job.running,
            "done": job.done,
            "total": job.total,
            "error": job.error,
            "xlsx": job.xlsx,
            "seconds": job.seconds,
            "entries": [
                entry_payload(e)
                for e in sorted(job.entries.values(), key=lambda e: e.filename.casefold())
            ],
        }


def run_analysis(folder: Path, images: list[Path]):

    def on_result(row, done, total):
        e = row["_image_data"]
        with job.lock:
            # save right away: an interrupted run keeps what it has done
            scan.store_result(folder, e)
            e.review = job.reviews.get(e.filename)
            job.entries[e.filename] = e
            job.done = done
            job.total = total
        print(f"[{done}/{total}] {row['Filename']}: {row['Status']}", flush=True)

    t0 = time.perf_counter()

    try:
        results = scan.analyze_folder(folder, on_result, images)
        seconds = time.perf_counter() - t0
        with job.lock:
            paths = scan.export_results(folder, results, seconds)
            job.xlsx = str(paths["xlsx"])
            job.seconds = seconds

    except Exception as e:
        with job.lock:
            job.error = f"{type(e).__name__}: {e}"

    finally:
        with job.lock:
            job.running = False


def start_analysis(folder_text: str, mode: str = "new") -> tuple[int, dict]:
    """
    Open a folder: show saved results, analyse new / changed plans
    (mode "new") or all plans again (mode "all").
    """

    folder_text = folder_text.strip().strip('"')

    if not folder_text:
        return 400, {"error": "Choose a folder first."}

    if mode not in ("new", "all"):
        return 400, {"error": f"Unknown mode: {mode}"}

    folder = Path(folder_text).expanduser().resolve()

    if not folder.is_dir():
        return 400, {"error": f"Folder not found: {folder}"}

    if not scan.find_images(folder):
        return 400, {"error": f"No images or PDFs in this folder: {folder}"}

    with job.lock:

        if job.running:
            return 409, {"error": "An analysis is already running. Wait until it has finished."}

        try:
            notes = scan.open_folder(folder)
            entries = scan.current_entries(folder)
            reviews = store.load_reviews(folder)
            todo = scan.images_to_analyse(folder, entries, everything=(mode == "all"))
        except Exception as e:
            return 400, {"error": f"Saved data for this folder cannot be read: {type(e).__name__}: {e}"}

        job.folder = folder
        job.mode = mode
        job.entries = entries
        job.reviews = reviews
        job.notes = notes
        job.loaded = len(entries)
        job.pending = len(todo)
        job.running = bool(todo)
        job.done = 0
        job.total = len(todo)
        job.error = None
        job.xlsx = str(store.folder_dir(folder) / scan.XLSX_FILENAME)
        job.seconds = None

    if todo:
        threading.Thread(target=run_analysis, args=(folder, todo), daemon=True).start()

    return 202, {"loaded": len(entries), "pending": len(todo)}


# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # keep the console for analysis progress

    def send(self, status: int, body: bytes, content_type: str, headers: dict | None = None):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The browser cancelled the request, e.g. the user went to the
            # next plan while the original-resolution image was loading.
            pass

    def send_json(self, status: int, data):
        self.send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    # --------------------------------------------------------

    def do_GET(self):

        url = urlparse(self.path)
        query = parse_qs(url.query)

        if url.path == "/":
            self.send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")

        elif url.path == "/api/state":
            self.send_json(200, state_payload())

        elif url.path == "/api/search":
            q = (query.get("q") or [""])[0]
            with job.lock:
                # search the reviewed values
                entries = [
                    {"filename": e.filename, "metadata": {f: e.value(f) for f in FIELDS}}
                    for e in job.entries.values()
                ]
            hits = search(entries, q)
            self.send_json(200, {
                "query": q,
                "hits": [
                    {"filename": h.filename, "score": round(h.score, 3), "field": h.field, "reason": h.reason}
                    for h in hits
                ],
            })

        elif url.path == "/api/image":
            self.send_image(
                (query.get("file") or [""])[0],
                full=(query.get("full") or ["0"])[0] == "1"
            )

        elif url.path == "/api/export.xlsx":
            self.send_xlsx()

        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):

        url = urlparse(self.path)

        if url.path == "/api/pick-folder":
            try:
                result = subprocess.run(
                    [sys.executable, "-c", PICK_FOLDER_SCRIPT],
                    capture_output=True, text=True, timeout=600
                )
                folder = result.stdout.strip() or None
            except Exception as e:
                self.send_json(500, {"error": f"Folder dialog not available ({e}). Please paste the path."})
                return
            self.send_json(200, {"folder": folder})

        elif url.path == "/api/analyze":
            data = self.read_json()
            status, data = start_analysis(data.get("folder") or "", data.get("mode") or "new")
            self.send_json(status, data)

        elif url.path == "/api/review":
            data = self.read_json()
            with job.lock:
                e = job.entries.get(data.get("filename") or "")
            if e is None:
                self.send_json(404, {"error": "Plan not found"})
                return
            try:
                review = build_review(e, data)
            except ValueError as err:
                self.send_json(400, {"error": f"Invalid review: {err}"})
                return
            self.send_json(*store_review(e.filename, review))

        elif url.path == "/api/review/reset":
            self.send_json(*store_review(self.read_json().get("filename") or "", None))

        else:
            self.send_json(404, {"error": "Not found"})

    # --------------------------------------------------------

    def send_image(self, filename: str, full: bool = False):

        with job.lock:
            folder = job.folder
            known = filename in job.entries

        # Only files of the analysed folder, no paths
        if folder is None or not known or Path(filename).name != filename:
            self.send_json(404, {"error": "Plan not found"})
            return

        try:
            if full:
                # original resolution
                data, mime = scan.load_full_image(folder / filename, scan.get_cache_dir(folder))
            else:
                data, _, _ = scan.load_image(folder / filename, scan.get_cache_dir(folder))
                mime = "image/jpeg"
        except Exception as e:
            self.send_json(500, {"error": f"The plan could not be loaded: {e}"})
            return

        self.send(200, data, mime)

    def send_xlsx(self):

        with job.lock:
            entries = list(job.entries.values())
            folder = job.folder
            seconds = job.seconds

        if not entries:
            self.send_json(400, {"error": "No results to export yet"})
            return

        buffer = io.BytesIO()
        write_xlsx(entries, buffer, scan.run_info(folder, seconds), folder)

        self.send(
            200,
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            {"Content-Disposition": f'attachment; filename="{scan.XLSX_FILENAME}"'},
        )


def main():

    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT

    try:
        server = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        print(
            f"Port {port} is already in use - probably the app is still running\n"
            f"(in another terminal, or started earlier). Either:\n"
            f"  - stop it there with Ctrl+C, or\n"
            f"  - stop it from here:   kill $(lsof -tiTCP:{port} -sTCP:LISTEN)\n"
            f"  - or use another port: python3 src/app.py --port {port + 1}",
            file=sys.stderr
        )
        sys.exit(1)

    url = f"http://{HOST}:{port}"

    print(f"Planarchiv running at {url}  (stop with Ctrl+C)", flush=True)
    print(f"Data: {store.DATA_DIR}", flush=True)

    # Reopen the folder of the last session: saved results appear at
    # once, only new or changed plans are analysed
    last = store.last_folder()
    if last is not None:
        status, data = start_analysis(str(last), "new")
        if status == 202:
            print(f"Reopened {last}: {data['loaded']} plans from saved results, {data['pending']} to analyse", flush=True)

    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
