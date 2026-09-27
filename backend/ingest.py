"""TCP NDTP receiver with a bounded latest-position snapshot and metrics."""
import json
import os
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ndtp import Decoder

lock = threading.Lock()
vehicles = {}
stats = {'bytesReceived': 0, 'framesReceived': 0, 'packetsReceived': 0, 'duplicates': 0,
         'latePackets': 0, 'invalidFixes': 0, 'suspectFixes': 0, 'errors': 0,
         'connections': 0, 'lastReceivedAt': None}
GPS_MAX_SPEED_KMH = float(os.getenv('GPS_MAX_SPEED_KMH', '160'))
GPS_RETAIN_SECONDS = int(os.getenv('GPS_RETAIN_SECONDS', '120'))


def accept_event(old, event, received_at):
    """Merge an NDTP update without allowing duplicate, late or implausible fixes to teleport a marker."""
    if old and (event['eventTime'] < old['eventTime'] or
                event['eventTime'] == old['eventTime'] and event['packetId'] == old['packetId']):
        return old
    merged = {**(old or {}), **event, 'receivedAt': received_at,
              'eventTime': event['eventTime'], 'packetId': event['packetId']}
    previous_fix_time = old.get('positionEventTime') if old else None
    if not event['locationValid']:
        if old and old.get('hasPosition'):
            merged['coordinates'] = old['coordinates']
            merged['positionEventTime'] = previous_fix_time
            merged['hasPosition'] = True
        else:
            merged['hasPosition'] = False
        merged['gpsStatus'] = 'poor' if event.get('gpsQuality') == 'poor' else 'lost'
        return merged
    if old and old.get('hasPosition'):
        dt = event['eventTime'] - (previous_fix_time or old['eventTime'])
        if dt <= 0:
            merged.update(coordinates=old['coordinates'], positionEventTime=previous_fix_time,
                          hasPosition=True, gpsStatus='suspect')
            return merged
        lon1, lat1 = old['coordinates']
        lon2, lat2 = event['coordinates']
        from math import radians, sin, cos, asin, sqrt
        dlat, dlon = radians(lat2-lat1), radians(lon2-lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
        distance = 6371 * 2 * asin(sqrt(min(1, a)))
        if distance / dt * 3600 > GPS_MAX_SPEED_KMH:
            merged.update(coordinates=old['coordinates'], positionEventTime=previous_fix_time,
                          hasPosition=True, gpsStatus='suspect')
            return merged
    merged.update(positionEventTime=event['eventTime'], hasPosition=True, gpsStatus='valid')
    return merged


def snapshot():
    with lock:
        now = time.time()
        return {**stats, 'vehicles': [{**v, 'ageSeconds': max(0, round(now-v['receivedAt'], 1)),
                                     'positionAgeSeconds': max(0, round(now-v.get('positionReceivedAt', v['receivedAt']), 1)),
                                     'stale': now-v['receivedAt'] > 10,
                                     'positionExpired': not v.get('hasPosition') or now-v.get('positionReceivedAt', v['receivedAt']) > GPS_RETAIN_SECONDS}
                                    for v in vehicles.values()]}


class PacketHandler(socketserver.BaseRequestHandler):
    def handle(self):
        decoder = Decoder()
        self.request.settimeout(120)
        with lock:
            stats['connections'] += 1
        try:
            while chunk := self.request.recv(65536):
                previous_errors, previous_frames = decoder.errors, decoder.frames
                events = decoder.feed(chunk)
                now = time.time()
                with lock:
                    stats['bytesReceived'] += len(chunk)
                    stats['framesReceived'] += decoder.frames - previous_frames
                    stats['errors'] += decoder.errors - previous_errors
                    for event in events:
                        stats['packetsReceived'] += 1
                        stats['lastReceivedAt'] = now
                        unit = event['unitId']
                        old = vehicles.get(unit)
                        updated = accept_event(old, event, now)
                        if updated is old:
                            if old and event['eventTime'] == old['eventTime'] and event['packetId'] == old['packetId']:
                                stats['duplicates'] += 1
                            else:
                                stats['latePackets'] += 1
                            continue
                        if not event['locationValid']:
                            stats['invalidFixes'] += 1
                        if updated.get('gpsStatus') in ('suspect', 'poor'):
                            stats['suspectFixes'] += 1
                        if unit not in vehicles and len(vehicles) >= 10000:
                            del vehicles[min(vehicles, key=lambda key: vehicles[key]['receivedAt'])]
                        if updated.get('hasPosition') and updated.get('gpsStatus') == 'valid':
                            updated['positionReceivedAt'] = now
                        elif old and old.get('positionReceivedAt'):
                            updated['positionReceivedAt'] = old['positionReceivedAt']
                        vehicles[unit] = updated
        except (OSError, TimeoutError):
            pass
        finally:
            with lock:
                stats['connections'] -= 1
                if decoder.buffer:
                    stats['errors'] += 1


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/replay/reset':
            self.send_error(404)
            return
        # The replay controller closes its sockets before starting a new timeline.
        with lock:
            vehicles.clear()
            for key in stats:
                if key != 'connections':
                    stats[key] = None if key == 'lastReceivedAt' else 0
        self.send_response(204)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            body, content = b'{"status":"ok","service":"ingest","mode":"ndtp"}', 'application/json'
        elif self.path == '/telemetry':
            body, content = json.dumps(snapshot()).encode(), 'application/json'
        elif self.path == '/metrics':
            state = snapshot()
            names = {'bytesReceived': 'ndtp_bytes_received_total', 'framesReceived': 'ndtp_frames_received_total',
                     'packetsReceived': 'ndtp_packets_received_total', 'duplicates': 'ndtp_duplicates_total',
                     'latePackets': 'ndtp_late_packets_total', 'invalidFixes': 'ndtp_invalid_gps_fixes_total',
                     'suspectFixes': 'ndtp_suspect_gps_fixes_total', 'errors': 'ndtp_errors_total', 'connections': 'ndtp_connections'}
            body = ''.join(f'# TYPE {name} {"gauge" if key == "connections" else "counter"}\n{name} {state[key]}\n' for key, name in names.items()).encode()
            content = 'text/plain; version=0.0.4'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    tcp = socketserver.ThreadingTCPServer(('0.0.0.0', int(os.getenv('NDTP_PORT', '9201'))), PacketHandler)
    threading.Thread(target=tcp.serve_forever, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('HEALTH_PORT', '9101'))), Handler).serve_forever()
