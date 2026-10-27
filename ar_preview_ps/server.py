# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Minimal local HTTP server for the phone (same Wi-Fi).

  /                 page with an AR link (rel="ar" opens AR Quick Look in AR mode)
  /version          number of the latest export, the page polls it and reloads
  /model_<n>.usdz   the exported file; a new name per export avoids the iOS cache
"""

import base64
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from string import Template

_server = None   # ThreadingHTTPServer while running
url = ""         # address encoded in the QR code

# Shared with the server thread. Written by publish() only.
state = {"version": 0, "file": "", "info": "", "lock_scale": True}

_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<rect width="100" height="100" rx="16" fill="#2d2d2d"/>'
    '<path d="M50 20 78 35v30L50 80 22 65V35zM22 35l28 15 28-15M50 50v30" fill="none" '
    'stroke="#e0e0e0" stroke-width="3" stroke-linejoin="round"/></svg>'
)
_ICON = "data:image/svg+xml;base64," + base64.b64encode(_ICON_SVG.encode()).decode()

_PAGE = Template("""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AR Preview</title>
<style>
body { margin: 0; background: #1e1e1e; color: #ddd; text-align: center;
       font: 18px -apple-system, Helvetica, sans-serif; }
a { display: block; width: 60vw; max-width: 300px; margin: 10vh auto 0; }
img { width: 100%; }
#info { color: #888; font-size: 14px; }
</style></head><body>
<a id="ar" rel="ar" href="$href"><img src="$icon"></a>
<p>Tap to open in AR</p>
<p id="info">$info</p>
<script>
const version = $version;
// Try to open AR without a tap. Safari may block it, then the tap is needed.
document.getElementById("ar").click();
// Reload when Blender exports a new version.
setInterval(async () => {
  try {
    const r = await fetch("/version", { cache: "no-store" });
    if (parseInt(await r.text()) !== version) location.reload();
  } catch (e) {
    document.getElementById("info").textContent = "Server stopped";
  }
}, 1500);
</script></body></html>
""")


def _page():
    href = "/model_%d.usdz" % state["version"]
    if state["lock_scale"]:
        href += "#allowsContentScaling=0"
    return _PAGE.substitute(href=href, icon=_ICON, info=state["info"], version=state["version"])


class _Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self._respond(send_body=True)

    def do_HEAD(self):
        self._respond(send_body=False)

    def _respond(self, send_body):
        path = self.path.split("?")[0]

        if path == "/":
            self._send(_page().encode("utf-8"), "text/html; charset=utf-8", send_body)
        elif path == "/version":
            self._send(str(state["version"]).encode(), "text/plain", send_body)
        elif path.startswith("/model_") and path.endswith(".usdz") and os.path.isfile(state["file"]):
            with open(state["file"], "rb") as f:
                self._send(f.read(), "model/vnd.usdz+zip", send_body)
        else:
            self.send_error(404)

    def _send(self, data, content_type, send_body):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # keep the Blender console quiet


def local_ip():
    """IP address of the network interface used for the local network.

    Connecting a UDP socket sends no packet, it only asks the OS
    which interface it would route through.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_running():
    return _server is not None


def publish(file_path, info, lock_scale):
    """Make a new export available. The page on the phone reloads itself."""
    state["file"] = file_path
    state["info"] = info
    state["lock_scale"] = lock_scale
    state["version"] += 1


def start(port, ip=""):
    """Start the server. Raises OSError if the port is taken."""
    global _server, url
    stop()

    _server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    url = "http://%s:%d/" % (ip or local_ip(), port)

    thread = threading.Thread(target=_server.serve_forever, daemon=True)
    thread.start()


def stop():
    global _server, url
    if _server is not None:
        _server.shutdown()
        _server.server_close()
    _server = None
    url = ""
