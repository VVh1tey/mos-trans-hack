import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from replay import Replay, timestamp


class StreamPredictionTests(unittest.TestCase):
    def test_receiver_restart_reconnects_and_retries_same_packet(self):
        replay = Replay('.', 'localhost', 9201, Mock(), '', '')
        old, new = Mock(), Mock()
        old.sendall.side_effect = BrokenPipeError('receiver restarted')
        replay.sockets[1] = old
        event = dict(unitId=1, eventTime=100, coordinates=[37.6, 55.7],
                     locationValid=True, speedKmh=20, heading=0, altitude=100)
        with patch('replay.socket.create_connection', return_value=new):
            replay.send(event)
        old.close.assert_called_once()
        self.assertEqual(new.sendall.call_count, 2)  # handshake, then navigation
        self.assertEqual(old.sendall.call_args, new.sendall.call_args)
        self.assertEqual(replay.sent, 1)
        self.assertIs(replay.sockets[1], new)

    def test_failed_reconnect_is_bounded_and_does_not_count_a_send(self):
        replay = Replay('.', 'localhost', 9201, Mock(), '', '')
        event = dict(unitId=1, eventTime=100, coordinates=[37.6, 55.7],
                     locationValid=True, speedKmh=20, heading=0, altitude=100)
        with patch('replay.socket.create_connection', side_effect=ConnectionRefusedError) as connect:
            with self.assertRaises(ConnectionRefusedError):
                replay.send(event)
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(replay.sent, 0)
        self.assertEqual(replay.sockets, {})

    def test_forecasts_eligible_stop_on_new_packets_with_cadence(self):
        requests = []

        def http(url, body):
            requests.append(body)
            return {'prediction': 25, 'model': 'test-model'}

        replay = Replay('.', 'localhost', 9201, http, '', 'http://ml')
        stop = {'id': 'stop-1', 'plannedAt': 1800, 'actualAt': 1850}
        replay.dataset = SimpleNamespace(target_stop=lambda vehicle, now: stop if 600 < 1800 - now <= 900 else None,
                                         context=lambda vehicle, now: {'observedDelaySeconds': 15})
        for now in (800, 1000, 1050, 1121):
            replay.predict_stream({'vehicleId': 'bus', 'eventTime': now})

        self.assertEqual(len(requests), 2)
        self.assertEqual([point['cur_dev_s'] for point in requests], [15, 15])
        self.assertTrue(all(600 < 1800 - timestamp(point['T']) <= 900 for point in requests))
        self.assertTrue(all('actualAt' not in point and 'target_delay_s' not in point for point in requests))
        self.assertTrue(all(prediction['source'] == 'stream' for prediction in replay.predictions.values()))

    def test_stream_actual_does_not_change_labeled_mae(self):
        replay = Replay('.', 'localhost', 9201, lambda url, body: {}, '', '')
        replay.dataset = SimpleNamespace(points={'label': {'_actual': 100, '_revealAt': 1900}},
                                         units={}, schedules={}, schedule_times=[], first_eligible_at=1000,
                                         start=0, end=2000, traffic_count=0, schedule_count=0)
        replay.current = 1900
        replay.predictions = {
            'label': {'sampleId': 'label', 'vehicleId': 'bus', 'at': 1000, 'targetAt': 1800,
                      'prediction': 90, 'model': 'test', 'source': 'labeled', '_actual': None, '_revealAt': None},
            'stream': {'sampleId': 'stream', 'vehicleId': 'bus', 'at': 1010, 'targetAt': 1800,
                       'prediction': 0, 'model': 'test', 'source': 'stream', '_actual': 100, '_revealAt': 1850},
        }
        state = replay.snapshot(None)
        self.assertEqual(state['maeSeconds'], 10)
        self.assertEqual(state['evaluatedCount'], 1)
        self.assertEqual(state['streamPredictionCount'], 1)
        self.assertEqual(state['predictions'][0]['absoluteError'], 100)


if __name__ == '__main__':
    unittest.main()
