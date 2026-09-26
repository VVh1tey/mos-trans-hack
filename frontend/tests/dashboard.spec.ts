import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
const review='../.impeccable/review';
test('network → new route tab → vehicle → pin → scenario',async({page,context})=>{
  await mkdir(review,{recursive:true});
  const errors:string[]=[];context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await expect(page.getByRole('heading',{name:'Обзор сети'})).toBeVisible();
  await expect(page.locator('.vehicle-marker').first()).toBeVisible();
  await page.waitForTimeout(1800);await page.screenshot({path:`${review}/desktop.png`,fullPage:true});
  const search=page.getByRole('textbox',{name:'Поиск маршрута или ТС'});
  await search.pressSequentially('небывалый');await expect(search).toHaveValue('небывалый');await expect(page.getByText('Маршруты не найдены')).toBeVisible();
  await page.getByRole('button',{name:'Очистить поиск'}).click();
  await page.locator('.route-link').first().click();await expect(page.locator('.route-preview')).toBeVisible();expect(context.pages()).toHaveLength(1);
  await page.screenshot({path:`${review}/route-preview-desktop.png`,fullPage:true});
  const popup=context.waitForEvent('page');await page.locator('.route-preview').getByRole('link',{name:'Перейти',exact:true}).click();const route=await popup;
  await route.waitForLoadState();await expect(route.locator('h1')).toContainText('Маршрут');
  await expect(route.locator('.vehicle-marker').first()).toBeVisible();await route.waitForTimeout(1000);
  await route.screenshot({path:`${review}/route-desktop.png`,fullPage:true});
  await route.getByRole('button',{name:/Добавить маршрут .* в избранное/}).click();await expect(route.getByRole('button',{name:/Убрать маршрут .* из избранного/})).toHaveAttribute('aria-pressed','true');
  await route.locator('.incident').first().click();await expect(route.locator('dialog')).toBeVisible();
  await route.getByRole('button',{name:'Отметить просмотренным'}).click();await expect(route.getByRole('button',{name:'Снять отметку просмотра'})).toBeVisible();
  await route.keyboard.press('Escape');await expect(route.locator('dialog')).not.toBeVisible();
  await route.getByRole('button',{name:'What-if',exact:true}).click();
  await expect(route.getByText('Проверьте решение до выпуска ТС')).toBeVisible();
  const scenarioResponse=route.waitForResponse(r=>r.url().endsWith('/scenario')&&r.request().method()==='POST');
  await route.getByRole('button',{name:'Рассчитать сценарий'}).click();expect((await scenarioResponse).status()).toBe(200);
  await expect(route.locator('.comparison')).toHaveCount(3);
  await route.getByRole('button',{name:'Добавить одно ТС'}).click();await expect(route.getByText('Параметры изменены.',{exact:false})).toBeVisible();
  await route.getByRole('button',{name:'Рассчитать сценарий'}).click();await expect(route.locator('.inline-warning')).toHaveCount(0);
  await route.evaluate(()=>{(document.activeElement as HTMLElement)?.blur();window.scrollTo(0,0);});await route.waitForTimeout(300);await route.screenshot({path:`${review}/scenario-desktop.png`,fullPage:true});
  await route.getByRole('button',{name:'История',exact:true}).click();await expect(route.getByRole('heading',{name:'Журнал прогнозов'})).toBeVisible();
  const download=route.waitForEvent('download');await route.getByRole('button',{name:'Экспорт CSV'}).click();expect((await download).suggestedFilename()).toBe('predictions-demo.csv');
  expect(errors).toEqual([]);
});
test('settings persist on API, risk recalculates, invalid requests rejected',async({page,request})=>{
  const original=await (await request.get('/api/dashboard/settings')).json();
  try{
    await page.goto('/?view=settings');await page.getByLabel('Средний риск, от (сек)').fill('600');await page.getByLabel('Высокий риск, от (сек)').fill('900');
    const saved=page.waitForResponse(r=>r.url().endsWith('/settings')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Сохранить настройки'}).click();expect((await saved).status()).toBe(200);
    const state=await (await request.get('/api/dashboard')).json();expect(state.summary.highRiskCount).toBe(0);expect(state.incidents).toHaveLength(0);
    expect((await request.post('/api/dashboard/settings',{data:{mediumDelaySeconds:900,highDelaySeconds:100}})).status()).toBe(400);
    expect((await request.get('/api/dashboard/routes/missing')).status()).toBe(404);
  }finally{await request.post('/api/dashboard/settings',{data:original});}
});
test('mobile overview, route and scenario fit viewport',async({page,request})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.locator('.vehicle-marker').first()).toBeVisible();await page.waitForTimeout(700);
  const beforeRefresh=(await(await request.get('/api/dashboard')).json()).generatedAt;const refreshResponse=page.waitForResponse(r=>r.url().includes('/api/dashboard?')&&r.request().method()==='GET');await page.getByRole('button',{name:'Обновить данные'}).click();expect((await refreshResponse).status()).toBe(200);await expect.poll(async()=>(await(await request.get('/api/dashboard')).json()).generatedAt).not.toBe(beforeRefresh);
  await expect(page.getByRole('button',{name:/Ночные маршруты 18/})).toHaveAttribute('aria-pressed','true');await expect(page.locator('.route-row')).toHaveCount(6);
  await page.getByRole('button',{name:/Дневные маршруты 0/}).click();await expect(page.locator('.route-row')).toHaveCount(0);await expect(page.locator('.metric').first()).toContainText('0');
  await page.getByRole('button',{name:/Все 18/}).click();await expect(page.locator('.route-row')).toHaveCount(6);
  await page.getByRole('button',{name:/Ночные маршруты 18/}).click();
  await expect(page.locator('.mobile-shortcuts').getByRole('link',{name:'Настройки'})).toBeVisible();
  await page.screenshot({path:`${review}/mobile.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const data=await(await request.get('/api/dashboard')).json();
  await page.goto(`/?view=routes&route=${data.routes[0].id}`);await expect(page.locator('.vehicle-marker').first()).toBeVisible();
  await page.getByRole('button',{name:/Добавить маршрут .* в избранное/}).click();await expect(page.locator('.sidebar .pinned-nav,.mobile-shortcuts .favorite-shortcut')).toHaveCount(0);
  await page.screenshot({path:`${review}/route-mobile.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.getByRole('button',{name:'What-if',exact:true}).click();await page.getByRole('button',{name:'Рассчитать сценарий'}).click();await expect(page.locator('.comparison')).toHaveCount(3);
  await page.screenshot({path:`${review}/scenario-mobile.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
test('API failure shows recovery, no fabricated fallback data',async({page})=>{
  await page.route('**/api/dashboard?*',route=>route.abort());await page.goto('/');
  await expect(page.getByText('Не удалось загрузить данные')).toBeVisible();await expect(page.getByRole('button',{name:'Повторить',exact:true})).toBeVisible();
  await expect(page.locator('.metric')).toHaveCount(0);await page.unroute('**/api/dashboard?*');
  await page.getByRole('button',{name:'Повторить',exact:true}).click();await expect(page.locator('.metric')).toHaveCount(5);
  await page.route('**/api/dashboard?*',route=>route.abort());await page.getByRole('button',{name:'Обновить данные',exact:true}).click();
  await expect(page.getByText('Нет связи с API. Показан последний полученный снимок.')).toBeVisible();await expect(page.locator('.metric')).toHaveCount(5);
});

test('multiple favorites stay first, persist, and star does not open details',async({page,context})=>{
  await page.goto('/?view=routes');await expect(page.locator('.route-row')).toHaveCount(18);
  const rows=page.locator('.route-row');const ids=[await rows.nth(8).getAttribute('data-route-id'),await rows.nth(12).getAttribute('data-route-id')];
  for(const id of ids) await page.locator(`[data-route-id="${id}"] .favorite-button`).click();
  await expect(page.locator('.route-preview')).toHaveCount(0);expect(context.pages()).toHaveLength(1);
  expect(await rows.evaluateAll(items=>items.slice(0,2).map(el=>el.getAttribute('data-route-id')))).toEqual(expect.arrayContaining(ids));
  await page.reload();await expect(page.locator('.favorite-row')).toHaveCount(2);
  await page.screenshot({path:`${review}/favorites-desktop.png`,fullPage:true});
  const another=await context.newPage();await another.goto('/?view=routes');await expect(another.locator('.favorite-row')).toHaveCount(2);
  await page.locator(`[data-route-id="${ids[0]}"] .favorite-button`).click();await expect(another.locator('.favorite-row')).toHaveCount(1);
  await page.setViewportSize({width:390,height:844});await page.locator('.route-link').first().click();await expect(page.locator('.route-preview')).toBeVisible();
  await page.screenshot({path:`${review}/route-preview-mobile.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.keyboard.press('Escape');await expect(page.locator('.route-preview')).toHaveCount(0);
});
