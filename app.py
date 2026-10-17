"""
Silicon Dreams Video Converter
Flask server that converts public YouTube / Facebook video URLs to
MP4, WEBM, MKV, AVI, MP3, M4A and WAV using yt-dlp + ffmpeg.

No accounts, no database. Files are written to a temporary folder,
streamed to the visitor, and deleted immediately afterwards.
"""
import os
import shutil
import tempfile
import threading
import time
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = BASE_DIR  # all website files live next to this script
# Only these files are served to visitors (keeps app.py, Dockerfile etc. private)
PUBLIC_FILES = {
    "index.html", "terms.html", "privacy.html", "404.html", "style.css", "script.js",
    "theme.js", "logo.svg", "icon-512.png", "apple-touch-icon.png", "og-image.png",
    "robots.txt", "sitemap.xml", "site.webmanifest", "config.js",
}

# ---------------------------------------------------------------- settings
MAX_DURATION = int(os.environ.get("MAX_DURATION_SECONDS", 3 * 3600))   # 3 hours
MAX_FILESIZE = int(os.environ.get("MAX_FILESIZE_MB", 2048)) * 1024 * 1024
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_JOBS", 3))
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_10MIN", 30))
TEMP_ROOT = os.environ.get("TEMP_DIR", tempfile.gettempdir())
TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"
# Websites allowed to use this converter from another address (comma-separated)
ALLOWED_ORIGINS = {o.strip().rstrip("/") for o in os.environ.get(
    "ALLOWED_ORIGINS", "https://oles.co.in,https://www.oles.co.in").split(",") if o.strip()}
# Set FFMPEG_PATH if FFmpeg isn't installed system-wide (e.g. a static build in your home folder)
_HOME_FFMPEG = os.path.join(os.path.expanduser("~"), "ffmpeg", "ffmpeg")
FFMPEG_PATH = (os.environ.get("FFMPEG_PATH")
               or (_HOME_FFMPEG if os.path.exists(_HOME_FFMPEG) else "")
               or shutil.which("ffmpeg") or "")
if os.path.isdir(FFMPEG_PATH):
    FFMPEG_PATH = os.path.join(FFMPEG_PATH, "ffmpeg")

ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
    "facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com",
    "fb.watch", "fb.com", "www.fb.com",
}

FORMATS = {
    "mp4":  {"kind": "video", "mime": "video/mp4"},
    "webm": {"kind": "video", "mime": "video/webm"},
    "mkv":  {"kind": "video", "mime": "video/x-matroska"},
    "avi":  {"kind": "video", "mime": "video/x-msvideo"},
    "mp3":  {"kind": "audio", "mime": "audio/mpeg"},
    "m4a":  {"kind": "audio", "mime": "audio/mp4"},
    "wav":  {"kind": "audio", "mime": "audio/wav"},
}
QUALITIES = {"best": None, "2160": 2160, "1440": 1440, "1080": 1080,
             "720": 720, "480": 480, "360": 360}

app = Flask(__name__, static_folder=None)
job_slots = threading.BoundedSemaphore(MAX_CONCURRENT)


# ---------------------------------------------------------------- helpers
class UserError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def client_ip():
    if TRUST_PROXY and request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr or "unknown"


_hits, _hits_lock = {}, threading.Lock()


def check_rate_limit():
    ip, now = client_ip(), time.time()
    with _hits_lock:
        recent = [t for t in _hits.get(ip, []) if now - t < 600]
        if len(recent) >= RATE_LIMIT:
            _hits[ip] = recent
            raise UserError("Too many requests. Please wait a few minutes and try again.", 429)
        recent.append(now)
        _hits[ip] = recent


def clean_url(raw):
    url = (raw or "").strip()
    if not url:
        raise UserError("Please paste a YouTube or Facebook video link.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in ALLOWED_HOSTS:
        raise UserError("Only YouTube and Facebook video links are supported.")
    if len(url) > 2048:
        raise UserError("That link is too long.")
    return url


def platform_of(url):
    host = (urlparse(url).hostname or "").lower()
    return "YouTube" if "youtu" in host else "Facebook"


_yt = None


def ytdlp():
    """Import yt-dlp on first use (keeps app start-up light on shared hosting)."""
    global _yt
    if _yt is None:
        import yt_dlp
        _yt = yt_dlp
    return _yt


def base_opts():
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "socket_timeout": 30, "retries": 3, "cachedir": False}
    if FFMPEG_PATH:
        opts["ffmpeg_location"] = os.path.dirname(FFMPEG_PATH)  # folder, so ffprobe is found too
    return opts


def friendly_error(err):
    text = str(err).lower()
    if "private" in text:
        return "This video is private and can't be converted."
    if "sign in" in text or "age" in text or "login" in text:
        return "This video requires a login (age-restricted or members-only)."
    if "not available" in text or "unavailable" in text or "removed" in text:
        return "This video is unavailable or has been removed."
    if "live" in text:
        return "Live streams can't be converted until they have ended."
    if "file is larger" in text or "max_filesize" in text:
        return "This file is too large. Try a lower quality."
    return "We couldn't process this link. Check that the video is public and try again."


def extract_info(url):
    with ytdlp().YoutubeDL({**base_opts(), "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise UserError("No video found at this link.")
        info = entries[0]
    if info.get("is_live"):
        raise UserError("Live streams can't be converted until they have ended.")
    if (info.get("duration") or 0) > MAX_DURATION:
        raise UserError(f"Videos longer than {MAX_DURATION // 3600} hours aren't supported.")
    return info


def cleanup_worker():
    """Safety net: remove any leftover job folders older than one hour."""
    while True:
        try:
            now = time.time()
            for name in os.listdir(TEMP_ROOT):
                path = os.path.join(TEMP_ROOT, name)
                if name.startswith("sdconv_") and os.path.isdir(path) \
                        and now - os.path.getmtime(path) > 3600:
                    shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
        time.sleep(600)


threading.Thread(target=cleanup_worker, daemon=True).start()


# ---------------------------------------------------------------- errors
@app.errorhandler(UserError)
def handle_user_error(e):
    return jsonify(error=e.message), e.status


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify(error="Not found"), 404
    return send_from_directory(PUBLIC_DIR, "404.html"), 404


@app.after_request
def cors_headers(resp):
    origin = (request.headers.get("Origin") or "").rstrip("/")
    if origin in ALLOWED_ORIGINS and request.path.startswith(("/api/", "/status")):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length, Content-Type"
        resp.headers["Access-Control-Max-Age"] = "86400"
        resp.headers.add("Vary", "Origin")
    return resp


@app.route("/api/<path:_>", methods=["OPTIONS"])
def cors_preflight(_):
    return "", 204


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data: https:; "
        "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'")
    if request.path.endswith((".css", ".js", ".svg", ".png")):
        resp.headers["Cache-Control"] = "public, max-age=604800"
    return resp


# ---------------------------------------------------------------- pages
@app.get("/")
def home():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/terms")
def terms():
    return send_from_directory(PUBLIC_DIR, "terms.html")


@app.get("/privacy")
def privacy():
    return send_from_directory(PUBLIC_DIR, "privacy.html")


@app.get("/<name>")
def public_file(name):
    if name not in PUBLIC_FILES:
        abort(404)
    return send_from_directory(PUBLIC_DIR, name)


@app.get("/status")
@app.get("/healthz")
def health():
    """Open /status in a browser to check the converter is set up correctly."""
    ffmpeg_ok = bool(FFMPEG_PATH) and os.path.exists(FFMPEG_PATH) and os.access(FFMPEG_PATH, os.X_OK)
    return jsonify(
        converter_running=True,
        ffmpeg_found=ffmpeg_ok,
        ffmpeg_path=FFMPEG_PATH or None,
        yt_dlp_version=ytdlp().version.__version__,
        temp_folder_writable=os.access(TEMP_ROOT, os.W_OK),
        ready=ffmpeg_ok and os.access(TEMP_ROOT, os.W_OK),
    )


# ---------------------------------------------------------------- API
@app.post("/api/info")
def api_info():
    check_rate_limit()
    url = clean_url((request.get_json(silent=True) or {}).get("url"))
    try:
        info = extract_info(url)
    except UserError:
        raise
    except Exception as e:  # yt-dlp errors
        raise UserError(friendly_error(e), 422)

    heights = sorted({f.get("height") for f in info.get("formats") or []
                      if f.get("height") and f.get("vcodec") not in (None, "none")},
                     reverse=True)
    return jsonify(
        title=info.get("title") or "Untitled video",
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel"),
        platform=platform_of(url),
        heights=[h for h in heights if h in QUALITIES.values()],
    )


@app.get("/api/download")
def api_download():
    check_rate_limit()
    url = clean_url(request.args.get("url"))
    fmt = (request.args.get("format") or "mp4").lower()
    quality = request.args.get("quality") or "best"
    if fmt not in FORMATS:
        raise UserError("Unsupported format.")
    if quality not in QUALITIES:
        raise UserError("Unsupported quality.")

    if not job_slots.acquire(blocking=False):
        raise UserError("Our servers are busy right now. Please try again in a minute.", 503)

    workdir = tempfile.mkdtemp(prefix="sdconv_", dir=TEMP_ROOT)
    try:
        opts = {**base_opts(),
                "outtmpl": os.path.join(workdir, "%(title).90B.%(ext)s"),
                "windowsfilenames": True,
                "max_filesize": MAX_FILESIZE}

        if FORMATS[fmt]["kind"] == "audio":
            opts["format"] = "bestaudio/best"
            pp = {"key": "FFmpegExtractAudio", "preferredcodec": fmt}
            if fmt == "mp3":
                pp["preferredquality"] = "192"
            opts["postprocessors"] = [pp]
        else:
            h = QUALITIES[quality]
            lim = f"[height<={h}]" if h else ""
            if fmt == "mp4":
                opts["format"] = (f"bv*{lim}[ext=mp4]+ba[ext=m4a]/b{lim}[ext=mp4]/"
                                  f"bv*{lim}+ba/b{lim}/b")
            elif fmt == "webm":
                opts["format"] = f"bv*{lim}[ext=webm]+ba[ext=webm]/bv*{lim}+ba/b{lim}/b"
            else:
                opts["format"] = f"bv*{lim}+ba/b{lim}/b"

            if fmt in ("mp4", "mkv"):
                opts["merge_output_format"] = fmt
                opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": fmt}]
            else:  # webm / avi need a real container conversion when the source differs
                opts["merge_output_format"] = "mkv" if fmt == "avi" else "webm"
                opts["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": fmt}]

        try:
            info = extract_info(url)
            with ytdlp().YoutubeDL(opts) as ydl:
                ydl.process_ie_result(info, download=True)
        except UserError:
            raise
        except Exception as e:
            raise UserError(friendly_error(e), 422)

        files = [os.path.join(workdir, f) for f in os.listdir(workdir)
                 if f.lower().endswith("." + fmt)]
        if not files:
            raise UserError("Conversion failed. Please try another format or quality.", 500)
        path = max(files, key=os.path.getsize)

        resp = send_file(path, mimetype=FORMATS[fmt]["mime"], as_attachment=True,
                         download_name=os.path.basename(path), max_age=0)
        resp.headers["Cache-Control"] = "no-store"
        resp.call_on_close(lambda: (shutil.rmtree(workdir, ignore_errors=True),
                                    job_slots.release()))
        return resp
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        job_slots.release()
        raise


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
