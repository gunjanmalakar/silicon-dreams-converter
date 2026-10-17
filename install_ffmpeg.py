# Silicon Dreams converter - one-click FFmpeg installer for shared hosting.
# In cPanel > Setup Python App > your app > "Execute python script",
# type  install_ffmpeg.py  and click "Run Script".
# It downloads a ready-made FFmpeg into  ~/ffmpeg/  (about 80 MB) and tests it.
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import Request, urlopen

URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
DEST = os.path.join(os.path.expanduser("~"), "ffmpeg")


def main():
    os.makedirs(DEST, exist_ok=True)
    print("Downloading FFmpeg (about 40 MB)...")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.xz")
    try:
        with urlopen(Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as r:
            shutil.copyfileobj(r, tmp, 1024 * 1024)
        tmp.close()
        print("Download complete:", os.path.getsize(tmp.name) // (1024 * 1024), "MB")

        print("Extracting ffmpeg and ffprobe...")
        found = []
        with tarfile.open(tmp.name, "r:xz") as tar:
            for member in tar:
                name = os.path.basename(member.name)
                if member.isfile() and name in ("ffmpeg", "ffprobe"):
                    src = tar.extractfile(member)
                    target = os.path.join(DEST, name)
                    with open(target, "wb") as out:
                        shutil.copyfileobj(src, out, 1024 * 1024)
                    os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    found.append(name)
        if "ffmpeg" not in found:
            print("FAIL: ffmpeg was not found inside the download.")
            return 1
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    out = subprocess.run([os.path.join(DEST, "ffmpeg"), "-version"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    first = out.stdout.splitlines()[0] if out.stdout else "(no output)"
    if out.returncode == 0:
        print("\nOK  FFmpeg installed and working:", first)
        print("OK  Location:", DEST)
        print("\nNext: click RESTART on this page, then open /status on your site.")
        return 0
    print("\nFAIL  FFmpeg was installed but won't run on this server:", first)
    return 1


if __name__ == "__main__":
    sys.exit(main())
