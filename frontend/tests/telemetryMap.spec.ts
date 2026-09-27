import { test, expect } from '@playwright/test';

test('map retains lost fixes, removes expired fixes and rejects invalid coordinates', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6XQAAAAASUVORK5CYII=', 'base64'),
  }));
  const vehicle = {
    unitId: 1, vehicleId: 'test-1', packetId: 1, eventTime: 100, receivedAt: 100,
    coordinates: [37.62, 55.75], locationValid: true, hasPosition: true,
    gpsStatus: 'valid', positionEventTime: 100, positionExpired: false,
    speedKmh: 20, heading: 90, altitude: 100, satellites: 8, ageSeconds: 0,
    stale: false, scheduleCount: 0, nextStop: null, observedDelaySeconds: null, prediction: null,
  };
  let vehicles = [vehicle];
  await page.route('**/api/dashboard/simulation', route => route.fulfill({ json: {
    source: 'test', available: true, running: true, started: true, completed: false,
    speed: 1, currentTime: 100, startTime: 0, endTime: 1000, session: 1,
    trafficRows: 100, scheduleRows: 10, vehicleCount: 1, scheduledVehicleCount: 1,
    sentRows: 1, scheduleReached: 0, progress: .1, predictionCount: 0,
    streamPredictionCount: 0, labeledPredictionCount: 0, predictionTotal: 0,
    evaluatedCount: 0, maeSeconds: null, predictions: [], ingestAvailable: true, errors: [],
    telemetry: { bytesReceived: 53, framesReceived: 1, packetsReceived: 1,
      errors: 0, connections: 1, lastReceivedAt: 100, vehicles },
  } }));
  await page.goto('/');
  const marker = page.locator('.replay-bus');
  await expect(marker).toHaveCount(1, { timeout: 15000 });
  await expect(marker).toBeVisible();
  await page.screenshot({ path: '../.impeccable/review/telemetry-map-desktop.png' });
  vehicles = [{ ...vehicle, locationValid: false, gpsStatus: 'lost' }];
  await expect(marker).toHaveClass(/gps-lost/);
  await page.setViewportSize({ width: 390, height: 844 });
  await marker.scrollIntoViewIfNeeded();
  await expect(marker).toBeVisible();
  await page.screenshot({ path: '../.impeccable/review/telemetry-map-mobile.png' });
  vehicles = [{ ...vehicle, positionExpired: true }];
  await expect(marker).toHaveCount(0);
  vehicles = [{ ...vehicle, coordinates: [37, 100] }];
  await page.waitForResponse('**/api/dashboard/simulation');
  await expect(marker).toHaveCount(0);
  vehicles = [vehicle];
  await expect(marker).toHaveCount(1);
  expect(errors).toEqual([]);
});
