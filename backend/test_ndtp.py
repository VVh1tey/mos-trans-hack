import struct
import unittest
from ndtp import Decoder, crc16


def frame(body, service=1, message=101, unit=1166336):
    payload = struct.pack('<HHHI', service, message, 1, 2) + body
    crc = crc16(payload)
    return struct.pack('<HHHHBIH', 0x7E7E, len(payload), 0, (crc & 255) << 8 | crc >> 8, 2, unit, 0) + payload


def nav(dop=224):
    return b'\0\0' + struct.pack('<IIIBBHHHHHBB', 1700000000, 376173210, 557551234, dop, 120, 42, 50, 180, 300, 150, 12, 2)


class NDTPTests(unittest.TestCase):
    def test_known_modbus_crc(self):
        self.assertEqual(crc16(b'123456789'), 0x4B37)

    def test_fragmentation_and_coalesced_handshake(self):
        handshake = frame(struct.pack('<HHHIII', 6, 2, 0, 1166336, 65535, 0), service=0, message=100)
        realtime = frame(nav())
        decoder = Decoder()
        events = []
        for byte in handshake + realtime:
            events.extend(decoder.feed(bytes([byte])))
        self.assertEqual(len(events), 1)
        self.assertEqual(decoder.frames, 2)
        self.assertEqual(decoder.errors, 0)
        self.assertEqual(events[0]['coordinates'], [37.617321, 55.7551234])
        self.assertEqual(events[0]['speedKmh'], 42)
        self.assertEqual(len(decoder.feed(realtime * 3)), 3)

    def test_crc_rejection_and_recovery(self):
        damaged = bytearray(frame(nav()))
        damaged[-1] ^= 1
        decoder = Decoder()
        events = decoder.feed(b'junk' + damaged + frame(nav()))
        self.assertEqual(len(events), 1)
        self.assertEqual(decoder.errors, 2)

    def test_signed_coordinates_and_invalid_gps(self):
        event = Decoder().feed(frame(nav(dop=0)))[0]
        self.assertEqual(event['coordinates'], [-37.617321, -55.7551234])
        self.assertFalse(event['locationValid'])

    def test_corrupt_length_does_not_swallow_next_frame(self):
        damaged = bytearray(frame(nav()))
        struct.pack_into('<H', damaged, 2, len(damaged) * 2 - 15)
        decoder = Decoder()
        events = decoder.feed(damaged + frame(nav()))
        self.assertEqual(len(events), 1)
        self.assertEqual(decoder.errors, 1)
        self.assertFalse(decoder.buffer)

    def test_invalid_header_does_not_wait_for_advertised_length(self):
        damaged = bytearray(frame(nav()))
        struct.pack_into('<H', damaged, 2, 65535)
        damaged[8] = 99
        decoder = Decoder()
        self.assertEqual(len(decoder.feed(damaged + frame(nav()))), 1)

    def test_every_split_boundary(self):
        packet = frame(nav())
        for split in range(len(packet) + 1):
            with self.subTest(split=split):
                decoder = Decoder()
                events = decoder.feed(packet[:split]) + decoder.feed(packet[split:])
                self.assertEqual(len(events), 1)
                self.assertEqual(decoder.errors, 0)

    def test_short_nav_and_invalid_size(self):
        decoder = Decoder()
        self.assertEqual(decoder.feed(frame(b'\0\0')), [])
        self.assertEqual(decoder.errors, 1)
        decoder.feed(b'~~\x01\x00' + bytes(11) + frame(nav()))
        self.assertEqual(decoder.frames, 1)


if __name__ == '__main__':
    unittest.main()
