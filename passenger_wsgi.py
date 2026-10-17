# Used by cPanel "Setup Python App" to start the converter.
# If the app can't start, this shows the reason in the browser instead of a blank
# "500 Internal Server Error", so setup problems are easy to see and fix.
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import app as application
except Exception:
    _error = traceback.format_exc()

    def application(environ, start_response):
        body = (
            "The Silicon Dreams converter could not start.\n\n"
            "Python version: " + sys.version + "\n\n" + _error
        ).encode("utf-8")
        start_response("500 Internal Server Error",
                       [("Content-Type", "text/plain; charset=utf-8"),
                        ("Content-Length", str(len(body)))])
        return [body]
