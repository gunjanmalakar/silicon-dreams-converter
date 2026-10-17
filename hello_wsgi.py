# Minimal test app: if this page shows, the hosting can run Python websites.
import sys


def application(environ, start_response):
    body = ("Hello! Python web apps work on this hosting.\n\n"
            "Python: " + sys.version.split()[0] + "\n"
            "Interpreter: " + sys.executable + "\n").encode("utf-8")
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8"),
                              ("Content-Length", str(len(body)))])
    return [body]
