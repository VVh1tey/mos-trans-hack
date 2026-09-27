"""NDTP 6.2 framing and Nav00 decoding for the supplied emulator."""
import struct


def encode_frame(unit, request, body, service=1, message=101):
    payload = struct.pack('<HHHI', service, message, 1, request & 0xFFFFFFFF) + body
    crc = crc16(payload)
    return struct.pack('<HHHHBIH', 0x7E7E, len(payload), 0, (crc & 255) << 8 | crc >> 8, 2, unit, 0) + payload


def encode_handshake(unit):
    return encode_frame(unit, 1, struct.pack('<HHHIII', 6, 2, 0, unit, 65535, 0), 0, 100)


def encode_navigation(event, request):
    lon, lat = event['coordinates']
    dop = (64 if lon >= 0 else 0) | (32 if lat >= 0 else 0) | (128 if event['locationValid'] else 0)
    speed = max(0, min(65535, round(event['speedKmh'])))
    payload = struct.pack('<IIIBBHHHHHBB', int(event['eventTime']), round(abs(lon)*1e7), round(abs(lat)*1e7),
                          dop, 0, speed, speed, round(event['heading']) % 360, 0,
                          max(0, min(65535, round(event['altitude']))), 0, 0)
    return encode_frame(event['unitId'], request, b'\0\0' + payload)


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def decode(frame):
    if len(frame) < 25:
        raise ValueError('short frame')
    signature, size, flags, crc, kind, unit, _ = struct.unpack_from('<HHHHBIH', frame)
    if signature != 0x7E7E or kind != 2 or flags != 0 or size != len(frame) - 15:
        raise ValueError('invalid NPL header')
    expected = crc16(frame[15:])
    if crc != ((expected & 255) << 8 | expected >> 8):
        raise ValueError('CRC mismatch')
    service, message, _, request = struct.unpack_from('<HHHI', frame, 15)
    if (service, message) == (0, 100):
        if size != 28 or struct.unpack_from('<I', frame, 31)[0] != unit:
            raise ValueError('invalid handshake')
        return None
    if (service, message) != (1, 101):
        return None
    # The emulator guarantees Nav00 is first. Other sensor cells are optional.
    if len(frame) < 53 or frame[25] != 0:
        raise ValueError('missing Nav00')
    timestamp, lon, lat, dop, battery, speed, maximum, course, track, altitude, nsat, pdop = struct.unpack_from('<IIIBBHHHHHBB', frame, 27)
    if lon > 1800000000 or lat > 900000000 or course > 360:
        raise ValueError('invalid navigation coordinates/course')
    coordinates = [lon / 1e7 * (1 if dop & 64 else -1), lat / 1e7 * (1 if dop & 32 else -1)]
    gps_valid = bool(dop & 128)
    quality_poor = (0 < nsat < 4) or (0 < pdop > 20)
    quality_known = nsat > 0 or pdop > 0
    return {'unitId': unit, 'packetId': request, 'eventTime': timestamp,
            'coordinates': coordinates,
            'locationValid': gps_valid and not quality_poor,
            'gpsQuality': 'invalid' if not gps_valid else 'poor' if quality_poor else 'good' if quality_known else 'unknown',
            'pdop': pdop, 'speedKmh': speed, 'heading': course,
            'altitude': altitude, 'satellites': nsat}


class Decoder:
    """Each TCP connection owns a buffer: reads need not align with frames."""
    def __init__(self):
        self.buffer = bytearray()
        self.errors = 0
        self.frames = 0

    def feed(self, data):
        self.buffer.extend(data)
        events = []
        while len(self.buffer) >= 15:
            if self.buffer[:2] != b'~~':
                index = self.buffer.find(b'~~', 1)
                del self.buffer[:index if index >= 0 else len(self.buffer)-1]
                self.errors += 1
                continue
            size = struct.unpack_from('<H', self.buffer, 2)[0]
            flags = struct.unpack_from('<H', self.buffer, 4)[0]
            if size < 10 or flags != 0 or self.buffer[8] != 2:
                del self.buffer[:2]
                self.errors += 1
                continue
            if len(self.buffer) < 15 + size:
                break
            frame = bytes(self.buffer[:15+size])
            try:
                event = decode(frame)
                del self.buffer[:15+size]
                self.frames += 1
                if event is not None:
                    events.append(event)
            except ValueError:
                # The length field is not protected by the payload CRC. Never
                # discard that advertised length on failure: it may include
                # the beginning (or entirety) of the next healthy frame.
                del self.buffer[:2]
                index = self.buffer.find(b'~~')
                del self.buffer[:index if index >= 0 else max(0, len(self.buffer)-1)]
                self.errors += 1
        return events
