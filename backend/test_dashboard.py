import unittest
import tempfile
import json
from pathlib import Path
import dashboard


class DashboardTests(unittest.TestCase):
    def test_aggregate_matches_vehicles_and_routes(self):
        data = dashboard.snapshot()
        vehicles = [v for r in data['routes'] for v in r['vehicles']]
        self.assertEqual(data['summary']['activeVehicles'], len(vehicles))
        self.assertEqual(data['summary']['highRiskCount'], sum(v['risk'] == 'high' for v in vehicles))
        self.assertEqual(data['summary']['incidentCount'], len(data['incidents']))
        self.assertEqual(len({v['alertId'] for v in data['incidents']}), len(data['incidents']))
        for route in data['routes']:
            self.assertGreater(len(route['coordinates']), 2)
            self.assertGreater(len(route['stops']), 1)
            for x,y in route['coordinates']:
                self.assertTrue(35 < x < 40 and 54 < y < 58)

    def test_settings_reclassify_consistently(self):
        settings = dashboard.settings_from({**dashboard.SETTINGS, 'mediumDelaySeconds': 600, 'highDelaySeconds': 900})
        data = dashboard.snapshot(settings=settings)
        self.assertEqual(data['summary']['highRiskCount'], 0)
        self.assertFalse(data['incidents'])
        with self.assertRaises(ValueError):
            dashboard.settings_from({'mediumDelaySeconds': 300, 'highDelaySeconds': 100})

    def test_scenario_uses_parameters_and_validates(self):
        route = dashboard.snapshot()['routes'][0]
        body = {'extraVehicles': 1, 'horizonMinutes': 60, 'direction': 0, 'startStopId': route['stops'][0]['id'], 'startTime': '01:15'}
        one = dashboard.scenario(route['id'], body)
        two = dashboard.scenario(route['id'], {**body, 'extraVehicles': 2})
        self.assertLess(two['metrics'][0]['scenario'], one['metrics'][0]['scenario'])
        later_stop = dashboard.scenario(route['id'], {**body,'startStopId':route['stops'][-1]['id']})
        self.assertGreater(later_stop['metrics'][0]['scenario'], one['metrics'][0]['scenario'])
        for invalid in ({'extraVehicles': 0}, {'startTime': '99:99'}, {'startStopId': 'absent'}, {'direction': 3}, {'horizonMinutes': True}):
            with self.assertRaises(ValueError):
                dashboard.scenario(route['id'], {**body, **invalid})
        with self.assertRaises(KeyError):
            dashboard.snapshot(route_id='missing')

    def test_direction_and_history_window(self):
        route = dashboard.snapshot()['routes'][0]
        reverse = dashboard.snapshot(route_id=route['id'], direction=1, period=180)
        self.assertNotEqual(reverse['routes'][0]['coordinates'], route['coordinates'])
        points = reverse['history']
        from datetime import datetime
        elapsed = datetime.fromisoformat(points[-1]['time'])-datetime.fromisoformat(points[0]['time'])
        self.assertEqual(elapsed.total_seconds(), 180*60)

    def test_service_type_filter_metadata_and_fictional_plan_removed(self):
        data = dashboard.snapshot()
        self.assertTrue(all(route['serviceType'] == 'night' for route in data['routes']))
        self.assertNotIn('plannedVehicles', data['summary'])
        self.assertEqual(data['summary']['routeCount'], len(data['routes']))

    def test_imported_json_routes_are_merged_and_override_by_id(self):
        route = json.loads(json.dumps(dashboard.CATALOG['routes'][0]))
        route['serviceType'] = 'day'
        with tempfile.TemporaryDirectory() as folder:
            old = dashboard.IMPORT_DIR
            try:
                dashboard.IMPORT_DIR = Path(folder)
                (Path(folder) / 'day.json').write_text(json.dumps({'routes': [route]}), encoding='utf-8')
                data = dashboard.snapshot()
                self.assertEqual(len(data['routes']), len(dashboard.CATALOG['routes']))
                self.assertEqual(data['routes'][0]['serviceType'], 'day')
            finally:
                dashboard.IMPORT_DIR = old


if __name__ == '__main__':
    unittest.main()
