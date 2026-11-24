/* eslint-disable @typescript-eslint/no-require-imports -- plain Node script, run outside Next.js */
const { chromium } = require('playwright');
/**
 * Admin panel smoke test against a running stack (real API + database).
 *
 *   ADMIN_EMAIL=owner@example.uz ADMIN_PASSWORD=... BASE_URL=http://localhost:3000 \
 *     node frontend/e2e/admin-smoke.cjs /tmp/screenshots
 *
 * Creates test data (a category, product, promo code, delivery rate) with a unique suffix.
 * Never run it against production.
 */
const BASE = process.env.BASE_URL || 'http://localhost:3000';
const EMAIL = process.env.ADMIN_EMAIL;
const PASSWORD = process.env.ADMIN_PASSWORD;
if (!EMAIL || !PASSWORD) {
  console.error('Set ADMIN_EMAIL and ADMIN_PASSWORD');
  process.exit(2);
}
const out = process.argv[2] || '.';
const stamp = Date.now().toString().slice(-6);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const errors = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  const step = async (name, fn) => {
    try { await fn(); console.log('✓', name); }
    catch (e) { console.log('✗', name, '-', e.message.split('\n')[0]); await page.screenshot({ path: `${out}/fail-${name.replace(/\W+/g, '_')}.png` }); throw e; }
  };
  const toast = (text) => page.getByText(text).first().waitFor({ timeout: 10000 });

  await step('anonymous visit redirects to login', async () => {
    await page.goto(BASE + '/orders');
    await page.waitForURL('**/login', { timeout: 15000 });
  });
  await step('wrong password shows Uzbek error', async () => {
    await page.getByLabel('Email').fill(EMAIL);
    await page.getByLabel('Parol').fill('wrong-password');
    await page.getByRole('button', { name: 'Kirish' }).click();
    await page.getByRole('alert').filter({ hasText: 'noto‘g‘ri' }).waitFor();
  });
  await step('login and dashboard with real numbers', async () => {
    await page.getByLabel('Parol').fill(PASSWORD);
    await page.getByRole('button', { name: 'Kirish' }).click();
    await page.getByRole('heading', { name: 'Bosh sahifa' }).waitFor({ timeout: 15000 });
    await page.getByText('Bugungi tushum').waitFor();
    await page.getByText('Tizim ishlayapti').waitFor({ timeout: 10000 });
    await page.screenshot({ path: `${out}/dashboard.png` });
  });
  await step('session survives a page reload (refresh cookie)', async () => {
    await page.reload();
    await page.getByRole('heading', { name: 'Bosh sahifa' }).waitFor({ timeout: 15000 });
  });
  const catName = `Kiyimlar ${stamp}`;
  await step('create category', async () => {
    await page.getByRole('link', { name: 'Kategoriyalar' }).click();
    await page.getByRole('button', { name: 'Yangi kategoriya' }).click();
    await page.getByLabel('Nomi').fill(catName);
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await toast('Kategoriya saqlandi');
    await page.getByRole('cell', { name: catName }).waitFor();
  });
  const sku = `KYL-${stamp}`;
  await step('create product with variant and stock (validation first)', async () => {
    await page.getByRole('link', { name: 'Mahsulotlar' }).click();
    await page.getByRole('link', { name: 'Yangi mahsulot' }).click();
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await page.getByText('Nomini kiriting').waitFor();
    await page.getByLabel('Nomi', { exact: true }).fill(`Erkaklar ko‘ylagi ${stamp}`);
    await page.getByLabel('Kategoriya').selectOption({ label: catName });
    await page.getByLabel('SKU (artikul)').fill(sku);
    await page.getByLabel('Narx (so‘m)').fill('185000');
    await page.getByLabel('Chegirma narxi').fill('200000');
    await page.getByLabel('Boshlang‘ich qoldiq').fill('12');
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await page.getByText('asosiy narxdan kichik').waitFor();
    await page.getByLabel('Chegirma narxi').fill('159000');
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await toast('Mahsulot yaratildi');
    await page.getByRole('heading', { name: `Erkaklar ko‘ylagi ${stamp}` }).waitFor();
    await page.getByRole('cell', { name: sku }).waitFor();
  });
  await step('upload product image', async () => {
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64');
    await page.getByLabel('Rasm tanlash').setInputFiles({ name: 'rasm.png', mimeType: 'image/png', buffer: png });
    await toast('Rasm yuklandi');
    await page.getByText('Asosiy').first().waitFor();
  });
  await step('inventory adjust with reason and history', async () => {
    await page.getByRole('link', { name: 'Ombor' }).click();
    await page.getByLabel('Qidirish').fill(sku);
    const row = page.getByRole('row').filter({ hasText: sku });
    await row.getByRole('button', { name: 'O‘zgartirish' }).click();
    await page.getByLabel('O‘zgarish').fill('-20');
    await page.getByLabel('Sabab').fill('Inventarizatsiya');
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await toast('band');
    await page.getByLabel('O‘zgarish').fill('5');
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await toast('Qoldiq yangilandi');
    await row.getByRole('cell', { name: '17' }).first().waitFor();
    await row.getByRole('button', { name: 'Tarix' }).click();
    await page.getByRole('dialog').getByText('Inventarizatsiya').waitFor();
    await page.keyboard.press('Escape');
  });
  await step('delivery rate for Toshkent shahri', async () => {
    await page.getByRole('link', { name: 'Yetkazib berish' }).click();
    await page.getByRole('button', { name: 'Tarif qo‘shish' }).click();
    const dlg = page.getByRole('dialog');
    await dlg.getByLabel('Usul').selectOption({ label: 'Kuryer orqali yetkazib berish' });
    await dlg.getByLabel('Hudud').selectOption({ label: 'Toshkent shahri' });
    await dlg.getByLabel('Narx (so‘m)').fill('25000');
    await dlg.getByLabel('Bepul yetkazish (so‘mdan)').fill('500000');
    await dlg.getByRole('button', { name: 'Saqlash' }).click();
    await page.getByText(/Tarif saqlandi|allaqachon bor/).first().waitFor({ timeout: 10000 });
    await page.keyboard.press('Escape');
    await page.getByRole('cell', { name: /Toshkent shahri/ }).first().waitFor();
  });
  await step('promo code create', async () => {
    await page.getByRole('link', { name: 'Promokodlar' }).click();
    await page.getByRole('button', { name: 'Yangi promokod' }).click();
    await page.getByLabel('Kod', { exact: true }).fill(`yoz${stamp}`);
    await page.getByLabel('Qiymati').fill('15');
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await toast('Promokod saqlandi');
    await page.getByRole('cell', { name: `YOZ${stamp}` }).waitFor();
  });
  await step('settings save', async () => {
    await page.getByRole('link', { name: 'Sozlamalar' }).click();
    await page.getByLabel('Aloqa telefoni').fill('+998 71 200 00 00');
    await page.getByRole('button', { name: 'Saqlash' }).click();
    await toast('Sozlamalar saqlandi');
  });
  await step('reports, orders, customers, staff, audit pages load', async () => {
    for (const [link, heading] of [['Hisobotlar', 'Hisobotlar'], ['Buyurtmalar', 'Buyurtmalar'], ['Mijozlar', 'Mijozlar'], ['Xodimlar', 'Xodimlar'], ['Amallar jurnali', 'Amallar jurnali']]) {
      await page.getByRole('link', { name: link }).click();
      await page.getByRole('heading', { name: heading }).waitFor();
    }
    await page.getByRole('cell', { name: 'inventory.adjust' }).first().waitFor();
    await page.screenshot({ path: `${out}/audit.png` });
  });
  await step('mobile layout has a menu drawer', async () => {
    await page.setViewportSize({ width: 390, height: 800 });
    await page.getByRole('link', { name: 'Bosh sahifa' }).isHidden();
    await page.getByRole('button', { name: 'Menyuni ochish' }).click();
    await page.getByRole('dialog').getByRole('link', { name: 'Buyurtmalar' }).click();
    await page.getByRole('heading', { name: 'Buyurtmalar' }).waitFor();
    await page.screenshot({ path: `${out}/mobile.png` });
    await page.setViewportSize({ width: 1280, height: 860 });
  });
  await step('logout returns to login and blocks the panel', async () => {
    await page.getByRole('button', { name: 'Chiqish' }).click();
    await page.waitForURL('**/login');
    await page.goto(BASE + '/');
    await page.waitForURL('**/login', { timeout: 15000 });
  });
  const unexpected = errors.filter((e) => !/401|Unauthorized|status of 4\d\d/.test(e));
  console.log('console errors:', unexpected.length ? unexpected : 'none');
  await browser.close();
})().catch(() => process.exit(1));
