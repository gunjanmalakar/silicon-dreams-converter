# Silicon Dreams converter - setup check.
# In cPanel > Setup Python App > your app > "Execute python script",
# type  setup_check.py  and click "Run Script". It installs the packages
# and prints what works and what doesn't.
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
results = []


def check(name, ok, detail=""):
    results.append(("OK  " if ok else "FAIL") + "  " + name + ("  -> " + detail if detail else ""))


print("Python:", sys.version.split()[0], "at", sys.executable)
check("Python 3.9 or newer", sys.version_info >= (3, 9), sys.version.split()[0])

# 1. Install packages and show the real pip error if it fails
print("\n--- Installing packages (this can take a minute) ---")
try:
    p = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r",
         os.path.join(HERE, "requirements.txt")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=600)
    lines = p.stdout.strip().splitlines()
    print("\n".join(lines[-25:]))
    if p.returncode == -9 or p.returncode == 137:
        check("Install packages", False, "pip was killed - the hosting memory limit (512 MB) is too small")
    else:
        check("Install packages", p.returncode == 0, "exit code %s" % p.returncode)
except Exception as e:
    check("Install packages", False, repr(e))

# 2. Can the converter's code load?
for mod in ("flask", "yt_dlp"):
    try:
        __import__(mod)
        check("Load " + mod, True)
    except Exception as e:
        check("Load " + mod, False, repr(e))
try:
    sys.path.insert(0, HERE)
    import app  # noqa: F401
    check("Load converter app.py", True)
except Exception as e:
    check("Load converter app.py", False, repr(e))

# 3. Conversion tool and temp space
ff = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
check("FFmpeg available", bool(ff), ff or "not installed on this hosting")
import tempfile
check("Temp folder writable", os.access(tempfile.gettempdir(), os.W_OK), tempfile.gettempdir())

# 4. Can this server reach YouTube and Facebook?
try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen
for site in ("https://www.youtube.com", "https://www.facebook.com"):
    try:
        r = urlopen(Request(site, headers={"User-Agent": "Mozilla/5.0"}), timeout=15)
        check("Reach " + site, True, "HTTP %s" % r.getcode())
    except Exception as e:
        check("Reach " + site, False, repr(e)[:120])

print("\n=========== SUMMARY ===========")
print("\n".join(results))
