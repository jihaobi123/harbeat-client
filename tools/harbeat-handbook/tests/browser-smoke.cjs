const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const projectRoot = path.resolve(__dirname, '../../..');
const handbookPath = path.join(projectRoot, 'docs/superpowers/specs/harbeat-mobile-product-handbook.html');
const chromePath = process.env.HARBEAT_CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const screenshotPath = process.env.HARBEAT_SCREENSHOT_PATH || '/tmp/harbeat-mobile-product-handbook.png';

const text = async (locator) => (await locator.textContent()).trim();
let browser;

(async () => {
  assert.equal(fs.existsSync(handbookPath), true, 'build the handbook before browser QA');
  assert.equal(fs.existsSync(chromePath), true, `Chrome was not found at ${chromePath}`);

  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(5000);
  const browserErrors = [];
  page.on('pageerror', (error) => browserErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });

  await page.goto(pathToFileURL(handbookPath).href, { waitUntil: 'load' });
  assert.match(await page.title(), /HarBeat/);
  assert.match(await text(page.locator('.handbook-hero h1')), /让舞者找歌/);

  await page.locator('.app-header [data-mode="prototype"]').click();
  assert.equal(await text(page.locator('.prototype-heading h1')), '首页');

  await page.locator('[data-scenario="discover"]').click();
  await page.locator('button[data-view="V02"]').last().click();
  await page.locator('button[data-track="trk-electric"]').click();
  assert.match(await text(page.locator('.detail-page h2')), /Electric Motion/);
  await page.locator('[data-action="open-save"]').click();
  await page.locator('[data-save-track="trk-electric"][data-playlist="pl-practice"]').click();
  await page.locator('.detail-page [data-view="V02"]').click();
  await page.locator('.music-tabs [data-view="V05"]').click();
  assert.match(await text(page.locator('.phone-screen')), /Electric Motion/);

  await page.locator('[data-scenario="import"]').click();
  await page.locator('[data-action="next-step"]').click();
  await page.locator('[data-import-mode="link"]').click();
  assert.match(await text(page.locator('.legal-note')), /不提供未经授权下载/);
  await page.locator('button[data-track="trk-midnight"]').click();
  assert.match(await text(page.locator('.resource-copy')), /仅元数据/);
  await page.locator('[data-action="open-save"]').click();
  await page.locator('[data-save-track="trk-midnight"][data-playlist="pl-late"]').click();
  await page.locator('[data-action="next-step"]').click();
  assert.match(await text(page.locator('.phone-screen')), /After Midnight/);

  await page.locator('[data-scenario="device"]').click();
  await page.locator('button[data-start-pairing]').click();
  await page.locator('#pairing-code').fill('3588');
  await page.locator('[data-action="submit-pairing"]').click();
  assert.match(await text(page.locator('.device-hero')), /HarBeat Stage 01/);
  await page.locator('[data-view="V09"]').click();
  await page.locator('[data-edit-pad="pad-4"]').click();
  assert.match(await text(page.locator('.pad-page')), /APP v4/i);
  await page.locator('[data-view="V08"]').click();
  await page.locator('[data-action="disconnect-device"]').click();
  await page.locator('[data-view="V09"]').click();
  await page.locator('[data-action="request-sync"]').click();
  assert.match(await text(page.locator('.toast')), /设备未连接/);
  await page.locator('[data-action="reconnect-device"]').click();
  await page.locator('[data-action="request-sync"]').click();
  assert.match(await text(page.locator('[role="dialog"]')), /同步并覆盖设备/);
  await page.locator('[data-action="confirm-sync"]').click();
  assert.match(await text(page.locator('.sync-button')), /设备版本已一致/);

  await page.locator('.app-header [data-mode="annotations"]').click();
  await page.locator('.scenario-nav [data-view="V04"]').click();
  assert.match(await text(page.locator('.annotation-panel')), /资源可用性 API/);

  await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: 'load' });
  const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(hasHorizontalOverflow, false, 'mobile layout should not overflow horizontally');
  assert.deepEqual(browserErrors, []);

  console.log(`Browser smoke QA passed; screenshot: ${screenshotPath}`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
}).finally(async () => {
  await browser?.close();
});
