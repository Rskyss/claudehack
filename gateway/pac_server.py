import os
#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAC = os.path.expanduser("~/.config/claude-residential/proxy.pac")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = open(PAC, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        try:
            with open(os.path.expanduser("~/.config/claude-residential/pac_server.log"), "a") as fh:
                fh.write("%s\n" % (fmt % args))
        except Exception:
            return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8899), Handler).serve_forever()
