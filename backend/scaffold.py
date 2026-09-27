"""Online process placeholders with health and Prometheus endpoints."""

import os
import resource
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROLE = os.environ["ROLE"]
PORT = int(os.environ["HEALTH_PORT"])
bytes_received = 0
counter_lock = threading.Lock()


def resident_memory_bytes():
    try:
        with open('/proc/self/statm', encoding='ascii') as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError, IndexError):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = f'{{"status":"ok","service":"{ROLE}","mode":"scaffold"}}\n'.encode()
            content_type = "application/json"
        elif self.path == "/metrics":
            body = f'# HELP scaffold_ready Service process is running.\n# TYPE scaffold_ready gauge\nscaffold_ready{{service="{ROLE}"}} 1\n'
            body += '# HELP process_cpu_seconds_total Total user and system CPU time spent in process.\n# TYPE process_cpu_seconds_total counter\n'
            body += f'process_cpu_seconds_total {time.process_time()}\n'
            body += '# HELP process_resident_memory_bytes Resident memory size in bytes.\n# TYPE process_resident_memory_bytes gauge\n'
            body += f'process_resident_memory_bytes {resident_memory_bytes()}\n'
            if ROLE == "ingest":
                with counter_lock:
                    total = bytes_received
                body += f'# HELP ndtp_bytes_received_total Raw TCP bytes received, before NDTP decoding.\n# TYPE ndtp_bytes_received_total counter\nndtp_bytes_received_total {total}\n'
            body = body.encode()
            content_type = "text/plain; version=0.0.4"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PacketHandler(socketserver.BaseRequestHandler):
    def handle(self):
        global bytes_received
        # Hold the socket and drain bytes. NDTP framing/CRC remains a team task.
        while chunk := self.request.recv(4096):
            with counter_lock:
                bytes_received += len(chunk)


if ROLE == "ingest":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    tcp = socketserver.ThreadingTCPServer(("0.0.0.0", 9201), PacketHandler)
    threading.Thread(target=tcp.serve_forever, daemon=True).start()

ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
