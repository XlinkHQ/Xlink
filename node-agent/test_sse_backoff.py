"""Regression: the event-stream listener only slept on an exception. A stream
that the panel or a proxy closed CLEANLY reconnected instantly in a hot loop —
measured at ~2,900 requests/second per node, a self-inflicted DoS at fleet
scale. Every disconnect must now back off."""

import http.server
import importlib.util
import os
import socketserver
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("agent_sse", os.path.join(_HERE, "xlink-agent.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_clean_eof_does_not_reconnect_in_a_hot_loop():
    hits = 0

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal hits
            hits += 1
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        m.BASE = f"http://127.0.0.1:{srv.server_address[1]}"
        threading.Thread(target=m.sse_listener, daemon=True).start()
        time.sleep(1.5)
    finally:
        srv.shutdown()
        srv.server_close()  # shutdown() alone leaves the listening socket open
    assert hits <= 3, f"{hits} reconnects in 1.5s — the listener is spinning"
