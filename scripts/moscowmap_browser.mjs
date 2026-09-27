// Persistent Playwright worker used when MoscowMap builds its catalog in JS.
// Input/output use one JSON object per line so the Python crawler can reuse a
// single browser process for the whole crawl.
import readline from 'node:readline';
import { chromium } from '../frontend/node_modules/playwright/index.mjs';

// Headed by default to behave like the user's regular browser and avoid the
// site's bot rules for headless automation. Set MOSCOWMAP_HEADLESS=1 on hosts
// without a desktop session.
const browser = await chromium.launch({ headless: process.env.MOSCOWMAP_HEADLESS === '1' });
const context = await browser.newContext({ locale: 'ru-RU' });
const page = await context.newPage();
await page.addInitScript(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
});
const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function collectCatalog(url) {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await sleep(1200);
  try { await page.waitForLoadState('networkidle', { timeout: 4000 }); } catch {}

  const found = new Set();
  const collect = async () => {
    for (const href of await page.locator('a[href]').evaluateAll((els) => els.map((el) => el.href))) {
      if (href) found.add(href);
    }
  };
  await collect();

  // The number range selector changes the route list client-side on some
  // catalog pages. Visit each range tab and retain its route links.
  const tabs = await page.locator('a,button,[role="tab"]').evaluateAll((els) =>
    els.map((el) => (el.innerText || el.textContent || '').trim())
      .filter((text) => /^(?:[\u0430-\u044f\u0451]+[-\u2013\u2014][\u0430-\u044f\u0451]+|\d{1,4}\s*[-\u2013\u2014]\s*\d{1,4}|\dxx|1000\+)$/i.test(text))
  );
  for (const text of new Set(tabs)) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await sleep(400);
      await page.getByText(text, { exact: true }).first().click({ timeout: 1500 });
      await sleep(250);
      await collect();
    } catch {}
  }

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await sleep(400);
  const showAll = page.getByText(/\u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c\s+\u0432\u0441\u0435/i).first();
  if (await showAll.count()) {
    try {
      await showAll.click({ timeout: 2000 });
      await sleep(500);
      await collect();
    } catch {}
  }

  const html = await page.content();
  const escaped = [...found].map((href) => `<a href="${href.replaceAll('&', '&amp;').replaceAll('"', '&quot;')}"></a>`).join('');
  return { html: html.replace(/<\/body>/i, `${escaped}</body>`), status: response?.status() ?? 200 };
}

for await (const line of rl) {
  if (!line.trim()) continue;
  try {
    const { url } = JSON.parse(line);
    const result = await collectCatalog(url);
    process.stdout.write(JSON.stringify(result) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify({ error: String(error) }) + '\n');
  }
}

await browser.close();
