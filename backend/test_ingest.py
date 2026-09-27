from http.client import HTTPConnection
import socket
import socketserver
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

import ingest
from ndtp import encode_navigation


def event(at=100, packet=1, coordinates=None, valid=True):
    return dict(unitId=1, packetId=packet, eventTime=at,
                coordinates=coordinates or [37.6, 55.7], locationValid=valid,
                speedKmh=20, heading=0, altitude=100)


class FixTests(unittest.TestCase):
    def test_repeated_fix_does_not_refresh_position(self):
        old = ingest.accept_event(None, event(), 1000)
        updated = ingest.accept_event(old, event(packet=2), 1050)
        self.assertEqual(updated['gpsStatus'], 'valid')
        self.assertEqual(updated['receivedAt'], 1050)
        self.assertEqual(updated['positionReceivedAt'], 1000)

    def test_bad_fixes_preserve_baseline_and_recover(self):
        old = ingest.accept_event(None, event(), 1000)
        lost = ingest.accept_event(old, event(101, 2, valid=False), 1001)
        suspect = ingest.accept_event(lost, event(102, 3, [38.6, 56.7]), 1002)
        self.assertEqual(suspect['gpsStatus'], 'suspect')
        self.assertEqual(suspect['coordinates'], old['coordinates'])
        self.assertEqual(suspect['positionReceivedAt'], 1000)
        recovered = ingest.accept_event(suspect, event(103, 4, [37.6001, 55.7001]), 1003)
        self.assertEqual(recovered['gpsStatus'], 'valid')
        self.assertEqual(recovered['positionReceivedAt'], 1003)

    def test_duplicate_and_late_packets_do_not_refresh(self):
        old = ingest.accept_event(None, event(), 1000)
        self.assertIs(ingest.accept_event(old, event(), 1010), old)
        self.assertIs(ingest.accept_event(old, event(99, 2), 1010), old)

    def test_epoch_zero_is_a_valid_fix_time(self):
        old = ingest.accept_event(None, event(0), 1000)
        lost = ingest.accept_event(old, event(100, 2, valid=False), 1001)
        recovered = ingest.accept_event(lost, event(101, 3, [37.61, 55.7]), 1002)
        self.assertEqual(recovered['gpsStatus'], 'valid')


class StreamTests(unittest.TestCase):
    def test_reset_fences_existing_tcp_connections(self):
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True

        def wait_for(predicate):
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(.01)
            self.fail('TCP receiver did not reach the expected state')

        with Server(('127.0.0.1', 0), ingest.PacketHandler) as tcp, \
                ThreadingHTTPServer(('127.0.0.1', 0), ingest.Handler) as http:
            threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (tcp, http)]
            for thread in threads:
                thread.start()
            # Exercise the public reset endpoint and actual fragmented TCP input.
            connection = HTTPConnection(*http.server_address)
            try:
                connection.request('POST', '/replay/reset')
                self.assertEqual(connection.getresponse().status, 204)
                with socket.create_connection(tcp.server_address) as sender:
                    packet = encode_navigation(event(), 1)
                    sender.sendall(packet[:7])
                    sender.sendall(packet[7:])
                    wait_for(lambda: ingest.snapshot()['packetsReceived'] == 1)
                    connection.request('POST', '/replay/reset')
                    self.assertEqual(connection.getresponse().status, 204)
                    sender.sendall(encode_navigation(event(101, 2), 2))
                    wait_for(lambda: ingest.snapshot()['connections'] == 0)
                    self.assertEqual(ingest.snapshot()['vehicles'], [])
                    self.assertEqual(ingest.snapshot()['packetsReceived'], 0)
                with socket.create_connection(tcp.server_address) as sender:
                    sender.sendall(packet)
                    wait_for(lambda: ingest.snapshot()['packetsReceived'] == 1)
                    self.assertEqual(len(ingest.snapshot()['vehicles']), 1)
            finally:
                connection.close()
                tcp.shutdown()
                http.shutdown()
                for thread in threads:
                    thread.join()
