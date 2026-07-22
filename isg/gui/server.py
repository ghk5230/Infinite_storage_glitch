"""Local web GUI: Flask backend around the isg engine.

Long operations run in worker threads registered in a job table; the
frontend polls /api/job/<id> for phase/progress until done.
"""

import os
import tempfile
import threading
import time
import uuid
import webbrowser

from flask import Flask, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename

from .. import decoder, encoder, simulate


JOB_TTL_SECONDS = 6 * 60 * 60
MAX_FINISHED_JOBS = 100
ALLOWED_BLOCKS = {8, 16}
ALLOWED_RESOLUTIONS = {(1280, 720), (1920, 1080)}
ALLOWED_BITRATES = {"4M", "2M", "1500k", "1M"}


def create_app(workdir: str | None = None) -> Flask:
    workdir = os.path.abspath(workdir or os.path.join(os.getcwd(), "isg_output"))
    uploads_dir = os.path.join(workdir, "uploads")
    files_dir = os.path.join(workdir, "files")
    os.makedirs(uploads_dir, exist_ok=True)
    os.makedirs(files_dir, exist_ok=True)

    app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"),
                static_url_path="")
    jobs: dict[str, dict] = {}
    jobs_lock = threading.Lock()

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": getattr(error, "description", "bad request")}), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "not found"}), 404

    def cleanup_jobs() -> None:
        now = time.time()
        with jobs_lock:
            stale = [
                jid for jid, job in jobs.items()
                if job.get("status") != "running"
                and now - job.get("created_at", now) > JOB_TTL_SECONDS
            ]
            for jid in stale:
                jobs.pop(jid, None)

            finished = sorted(
                (
                    (job.get("created_at", now), jid)
                    for jid, job in jobs.items()
                    if job.get("status") != "running"
                ),
                key=lambda item: item[0],
            )
            overflow = len(finished) - MAX_FINISHED_JOBS
            for _, jid in finished[:max(0, overflow)]:
                jobs.pop(jid, None)

    def start_job(work) -> str:
        cleanup_jobs()
        jid = uuid.uuid4().hex[:12]
        job = {
            "status": "running",
            "phase": "starting",
            "progress": 0.0,
            "created_at": time.time(),
        }
        with jobs_lock:
            jobs[jid] = job

        def report(phase, frac):
            try:
                progress = float(frac)
            except (TypeError, ValueError):
                progress = -1.0
            progress = -1.0 if progress < 0 else min(progress, 1.0)
            with jobs_lock:
                job["phase"], job["progress"] = str(phase), progress

        def run():
            try:
                result = work(report)
                with jobs_lock:
                    job["result"] = result
                    job["status"], job["progress"] = "done", 1.0
                    job["phase"] = "complete"
            except Exception as e:
                with jobs_lock:
                    job["status"], job["error"] = "error", str(e)

        threading.Thread(target=run, daemon=True).start()
        return jid

    def save_upload(field: str) -> str:
        f = request.files.get(field)
        if f is None or not f.filename:
            abort(400, "no file uploaded")
        # Keep the original basename for metadata, isolated in a unique temp dir
        # so concurrent uploads and matching filenames never collide.
        name = secure_filename(os.path.basename(f.filename)) or "file.bin"
        directory = tempfile.mkdtemp(prefix="upload_", dir=uploads_dir)
        path = os.path.join(directory, name)
        f.save(path)
        return path

    def unique_path(path: str) -> str:
        if not os.path.exists(path):
            return path
        stem, ext = os.path.splitext(path)
        i = 2
        while os.path.exists(f"{stem}-{i}{ext}"):
            i += 1
        return f"{stem}-{i}{ext}"

    def parse_int(name: str, default: int, allowed: set[int] | None = None,
                  minimum: int | None = None) -> int:
        raw = request.form.get(name, str(default))
        try:
            value = int(raw)
        except (TypeError, ValueError):
            abort(400, f"{name} must be an integer")
        if allowed is not None and value not in allowed:
            abort(400, f"{name} must be one of: {', '.join(map(str, sorted(allowed)))}")
        if minimum is not None and value < minimum:
            abort(400, f"{name} must be at least {minimum}")
        return value

    def parse_resolution() -> tuple[int, int]:
        raw = request.form.get("res", "1280x720")
        width, sep, height = raw.partition("x")
        if sep != "x":
            abort(400, "res must look like 1280x720")
        try:
            parsed = (int(width), int(height))
        except ValueError:
            abort(400, "res must use integer dimensions")
        if parsed not in ALLOWED_RESOLUTIONS:
            allowed = ", ".join(f"{w}x{h}" for w, h in sorted(ALLOWED_RESOLUTIONS))
            abort(400, f"res must be one of: {allowed}")
        return parsed

    def parse_bitrate() -> str:
        bitrate = request.form.get("bitrate", "2M")
        if bitrate not in ALLOWED_BITRATES:
            abort(400, f"bitrate must be one of: {', '.join(sorted(ALLOWED_BITRATES))}")
        return bitrate

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.post("/api/encode")
    def api_encode():
        block = parse_int("block", 8, allowed=ALLOWED_BLOCKS)
        width, height = parse_resolution()
        src = save_upload("file")
        password = request.form.get("password") or None
        out = unique_path(os.path.join(
            files_dir, os.path.splitext(os.path.basename(src))[0] + ".isg.mp4"))

        def work(report):
            stats = encoder.embed(src, out, block=block,
                                  width=width, height=height,
                                  password=password, progress=report)
            stats["file_path"] = out
            stats["file_name"] = os.path.basename(out)
            return stats

        return jsonify({"job": start_job(work)})

    @app.post("/api/decode")
    def api_decode():
        src = save_upload("file")
        password = request.form.get("password") or None
        out_dir = os.path.join(files_dir, "decoded", uuid.uuid4().hex[:8])
        os.makedirs(out_dir, exist_ok=True)

        def work(report):
            stats = decoder.extract(src, out_dir, password=password, progress=report)
            stats["file_path"] = stats["output_path"]
            stats["file_name"] = stats["filename"]
            return stats

        return jsonify({"job": start_job(work)})

    @app.post("/api/stress")
    def api_stress():
        bitrate = parse_bitrate()
        f = request.files.get("file")
        if f is not None and f.filename:
            src = save_upload("file")
        else:
            with jobs_lock:
                source = jobs.get(request.form.get("source_job", ""))
                source = dict(source) if source else None
            if not source or source.get("status") != "done":
                abort(400, "upload a video or encode one first")
            src = source.get("result", {}).get("file_path")
            if not src or not os.path.isfile(src):
                abort(400, "the encoded source video is no longer available")
        degraded = os.path.join(files_dir, f"stress_{bitrate}_{uuid.uuid4().hex[:6]}.mp4")

        def work(report):
            report(f"re-encoding at {bitrate} (simulated YouTube)", -1)
            simulate.reencode(src, degraded, bitrate)
            try:
                _, _, sha_ok = decoder.recover_payload(degraded, progress=report)
                survived, reason = sha_ok, None if sha_ok else "checksum mismatch after repair"
            except ValueError as e:
                survived, reason = False, str(e)
            return {
                "survived": survived,
                "reason": reason,
                "bitrate": bitrate,
                "original_bytes": os.path.getsize(src),
                "degraded_bytes": os.path.getsize(degraded),
                "file_path": degraded,
                "file_name": os.path.basename(degraded),
            }

        return jsonify({"job": start_job(work)})

    @app.get("/api/job/<jid>")
    def api_job(jid):
        cleanup_jobs()
        with jobs_lock:
            job = jobs.get(jid)
            job = dict(job) if job else None
        if job is None:
            abort(404)
        return jsonify(job)

    @app.get("/api/file/<jid>")
    def api_file(jid):
        with jobs_lock:
            job = jobs.get(jid)
            job = dict(job) if job else None
        result = job.get("result", {}) if job else {}
        if not job or job.get("status") != "done" or "file_path" not in result:
            abort(404)
        file_path = os.path.abspath(result["file_path"])
        if not os.path.isfile(file_path):
            abort(404)
        try:
            if os.path.commonpath([files_dir, file_path]) != files_dir:
                abort(404)
        except ValueError:
            abort(404)
        return send_file(file_path, conditional=True,
                         as_attachment="dl" in request.args,
                         download_name=result.get("file_name") or os.path.basename(file_path))

    @app.post("/api/open-folder")
    def api_open_folder():
        if hasattr(os, "startfile"):
            try:
                os.startfile(files_dir)
            except OSError as e:
                abort(400, str(e))
        return jsonify({"ok": True, "path": files_dir})

    return app


def run(port: int = 8765, open_browser: bool = True) -> None:
    app = create_app()
    url = f"http://127.0.0.1:{port}"
    print(f"  Infinite Storage Glitch GUI -> {url}   (Ctrl+C to stop)")
    if open_browser:
        timer = threading.Timer(1.0, webbrowser.open, [url])
        timer.daemon = True
        timer.start()
    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)