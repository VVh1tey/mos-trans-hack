import { test, expect } from '@playwright/test';

test('provided emulator: start, live positions, stop, stale data, restart', async ({ page, request }) => {
  test.skip(process.env.NDTP_LIVE_TEST !== '1', 'Requires Docker Compose with the provided emulator');
  test.setTimeout(90000);
  const endpoint = '/api/dashboard/simulation';
  const status = async () => (await request.get(endpoint)).json();
  await request.post(endpoint, { data: { action: 'stop' } });
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Симулятор NDTP' });
  await expect(panel.getByText('Симуляция остановлена', { exact: true })).toBeVisible();
  await panel.getByRole('button', { name: 'Запустить симуляцию' }).click();
  try {
    await expect(panel.getByText('Симуляция включена', { exact: true })).toBeVisible();
    await expect.poll(async () => (await status()).telemetry.vehicles.length).toBe(5);
    const first = await status();
    expect(first.telemetry.errors).toBe(0);
    await expect.poll(async () => (await status()).telemetry.packetsReceived).toBeGreaterThan(first.telemetry.packetsReceived);
    await expect.poll(async () => JSON.stringify((await status()).telemetry.vehicles.map((v: { coordinates: number[] }) => v.coordinates))).not.toBe(JSON.stringify(first.telemetry.vehicles.map((v: { coordinates: number[] }) => v.coordinates)));
    await expect(panel.locator('tbody tr')).toHaveCount(5);
    await expect(panel.locator('.telemetry-marker')).toHaveCount(5);
    await expect(panel.locator('.telemetry-map .map-canvas')).toHaveAttribute('data-settled', 'true');
    await page.screenshot({ path: '../.impeccable/review/ndtp-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(panel.getByRole('button', { name: 'Остановить', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: '../.impeccable/review/ndtp-mobile.png', fullPage: true });
    await panel.getByRole('button', { name: 'Остановить', exact: true }).click();
    await expect(panel.getByText('Симуляция остановлена', { exact: true })).toBeVisible();
    // Allow already in-flight TCP packets to drain, then prove the stream stopped.
    await expect.poll(async () => (await status()).telemetry.connections).toBe(0);
    const stopped = await status();
    await expect.poll(async () => (await status()).telemetry.vehicles.every((v: { stale: boolean }) => v.stale), { timeout: 20000 }).toBe(true);
    expect((await status()).telemetry.packetsReceived).toBe(stopped.telemetry.packetsReceived);
    await expect(panel.getByText('Нет свежих данных', { exact: true })).toHaveCount(5);
    await panel.getByRole('button', { name: 'Запустить симуляцию' }).click();
    await expect.poll(async () => (await status()).telemetry.packetsReceived).toBeGreaterThan(stopped.telemetry.packetsReceived);
    await page.reload();
    await expect(panel.getByText('Симуляция включена', { exact: true })).toBeVisible();
  } finally {
    await request.post(endpoint, { data: { action: 'stop' } });
  }
});

test('unavailable emulator is not presented as stopped', async ({ page }) => {
  await page.route('**/api/dashboard/simulation', route => route.fulfill({json:{available:false,running:null,unitCount:0,ingestAvailable:true,telemetry:null,errors:['Нет связи с эмулятором. Запустите сервис emulator и повторите.']}}));
  await page.goto('/');
  const panel = page.getByRole('region', {name:'Симулятор NDTP'});
  await expect(panel.getByText('Статус неизвестен', {exact:true})).toBeVisible();
  await expect(panel.getByRole('button', {name:'Запустить симуляцию'})).toBeDisabled();
  await expect(panel.getByRole('alert')).toContainText('Нет связи с эмулятором');
});
