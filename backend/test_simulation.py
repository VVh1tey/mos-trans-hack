import unittest
from unittest.mock import patch
from urllib.error import URLError

import simulation


class SimulationTests(unittest.TestCase):
    def test_control_delegates_action_and_speed_to_replay(self):
        expected = {'running': True, 'available': True}
        with patch.object(simulation.REPLAY, 'control') as replay_control, \
                patch.object(simulation, 'status', return_value=expected):
            self.assertIs(simulation.control('start', 60), expected)
        replay_control.assert_called_once_with('start', 60)

    def test_status_combines_ingest_snapshot_and_replay_state(self):
        telemetry = {'vehicles': []}
        expected = {'running': False, 'errors': [], 'telemetry': telemetry}
        with patch.object(simulation, 'request', return_value=telemetry) as request, \
                patch.object(simulation.REPLAY, 'snapshot', return_value=expected) as snapshot:
            self.assertIs(simulation.status(), expected)
        request.assert_called_once_with(simulation.INGEST_URL + '/telemetry')
        snapshot.assert_called_once_with(telemetry)

    def test_ingest_outage_is_reported_without_rewriting_replay_state(self):
        expected = {'running': True, 'errors': [], 'ingestAvailable': False}
        with patch.object(simulation, 'request', side_effect=URLError('offline')), \
                patch.object(simulation.REPLAY, 'snapshot', return_value=expected) as snapshot:
            state = simulation.status()
        self.assertTrue(state['running'])
        self.assertFalse(state['ingestAvailable'])
        self.assertEqual(len(state['errors']), 1)
        snapshot.assert_called_once_with(None)

    def test_unavailable_dataset_does_not_claim_stopped(self):
        with patch.object(simulation, 'request', return_value={'vehicles': []}), \
                patch.object(simulation.REPLAY, 'snapshot', side_effect=ValueError('dataset unavailable')):
            state = simulation.status()
        self.assertIsNone(state['running'])
        self.assertFalse(state['available'])
        self.assertEqual(len(state['errors']), 1)

    def test_rejects_unknown_action(self):
        with patch.object(simulation.REPLAY, 'control') as replay_control:
            with self.assertRaises(ValueError):
                simulation.control('restart')
        replay_control.assert_not_called()


if __name__ == '__main__':
    unittest.main()
