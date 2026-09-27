const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const base = 'http://127.0.0.1:18080';
  const out = path.resolve(__dirname, '../docs/screenshots');
  fs.mkdirSync(out, { recursive: true });
  const initial = await (await fetch(base + '/api/dashboard/simulation')).json();
  const control = async action => (await fetch(base + '/api/dashboard/simulation', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action}),
  })).json();
  const browser = await chromium.launch({headless: true, args: ['--enable-webgl', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  const page = await browser.newPage({viewport: {width: 1600, height: 1000}, deviceScaleFactor: 1});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const snap = async name => {
    await page.locator('.map-loading').waitFor({state: 'hidden', timeout: 30000});
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({path: path.join(out, name + '.png')});
    console.log(name, await page.title());
  };
  try {
    if (initial.running) await control('stop');
    await page.goto(base, {waitUntil: 'networkidle'});
    await page.locator('.replay-bus').first().waitFor({state: 'attached', timeout: 25000});
    await snap('01-network');
    const state = await (await fetch(base + '/api/dashboard/simulation')).json();
    const visible = state.telemetry.vehicles.filter(v => v.hasPosition && !v.positionExpired);
    const vehicle = visible.find(v => v.prediction) || visible[0];
    await page.locator(`.replay-bus[data-vehicle-id="${vehicle.vehicleId}"]`).click({force: true});
    await page.locator('.replay-forecast').waitFor();
    await page.locator('.map-and-attention').scrollIntoViewIfNeeded();
    await snap('02-vehicle');
    await page.goto(base + '/?view=routes', {waitUntil: 'networkidle'});
    await page.locator('.route-link').first().waitFor();
    await snap('03-routes');
    await page.locator('.route-link').first().click();
    const href = await page.locator('.route-preview a').getAttribute('href');
    await page.goto(new URL(href, base).href, {waitUntil: 'networkidle'});
    await page.locator('.vehicle-marker').first().waitFor();
    await snap('04-route');
    await page.getByRole('button', {name: 'What-if', exact: true}).click();
    await page.getByRole('button', {name: 'Рассчитать сценарий', exact: true}).click();
    await page.locator('.comparison').first().waitFor();
    await snap('05-scenario');
    await page.goto(base + '/?view=history', {waitUntil: 'networkidle'});
    await page.getByRole('heading', {name: 'Журнал прогнозов'}).waitFor();
    await snap('06-history');
    await page.goto(base + '/?view=settings', {waitUntil: 'networkidle'});
    await page.getByRole('heading', {name: 'Настройки риска'}).waitFor();
    await snap('07-settings');
    await page.goto(base + '/?view=incidents', {waitUntil: 'networkidle'});
    await page.locator('.incident').first().waitFor();
    await snap('08-incidents');
    const metadata = {capturedAt: new Date().toISOString(), source: base, viewport: {width: 1600, height: 1000},
      mockedResponses: false, model: vehicle.prediction?.model,
      predictionCount: state.predictionCount, currentTime: state.currentTime, errors};
    fs.writeFileSync(path.join(out, 'capture.json'), JSON.stringify(metadata, null, 2) + '\n');
    console.log(JSON.stringify(metadata));
    if (errors.length) process.exitCode = 1;
  } finally {
    await browser.close();
    if (initial.running) await control('start');
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
