import unittest
from types import SimpleNamespace

from replay import Replay, timestamp


class StreamPredictionTests(unittest.TestCase):
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
