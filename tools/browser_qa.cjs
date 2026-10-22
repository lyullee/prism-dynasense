// Real dashboard QA in a fresh headless browser, without a user profile.
// Usage: node tools/browser_qa.cjs <absolute Playwright module> <Chrome executable>
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require(process.argv[2] || 'playwright');
(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({ headless: true, ...(process.argv[3] ? { executablePath: process.argv[3] } : {}) });
  const report = pathToFileURL(path.join(root, 'examples/results/hydrogen/report.html')).href;
  fs.mkdirSync(path.join(root, 'docs/screenshots'), { recursive: true });
  fs.mkdirSync(path.join(root, 'artifacts'), { recursive: true });
  const results = [];
  try {
    for (const [name, width, height, colorScheme] of [['desktop', 1440, 1100, 'light'], ['mobile', 390, 844, 'light'], ['dark', 1280, 1000, 'dark']]) {
      const context = await browser.newContext({ viewport: { width, height }, colorScheme });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(report);
      await page.waitForFunction(() => document.documentElement.dataset.ready === 'true');
      await page.locator('#output-select').selectOption('conditional_harm_probability');
      const selected = await page.locator('#gate-status').innerText();
      await page.locator('#output-select').selectOption('thermal_dose');
      await page.locator('details summary').click();
      const details = await page.locator('details').evaluate(e => e.open);
      await page.locator('details summary').click();
      const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      const paths = await page.locator('.charts svg path').count();
      const metric = await page.locator('#mass-value').innerText();
      const svgLabelsClipped = await page.locator('#sobol-plot').evaluate(svg => {
        const v = svg.viewBox.baseVal;
        return [...svg.querySelectorAll('text')].some(text => { const b = text.getBBox(); return b.y < -1 || b.y+b.height > v.height+1 || b.x < -1 || b.x+b.width > v.width+1; });
      });
      await page.screenshot({ path: path.join(root, `docs/screenshots/${name}.png`), fullPage: true });
      const row = { name, width, height, errors, horizontalOverflow, paths, metric, selected, details, svgLabelsClipped };
      results.push(row);
      await context.close();
      if (errors.length || horizontalOverflow || paths !== 4 || !details || svgLabelsClipped) throw new Error(JSON.stringify(row));
    }
    fs.writeFileSync(path.join(root, 'artifacts/browser-qa.json'), JSON.stringify({ status: 'PASS', results }, null, 2));
    process.stdout.write(JSON.stringify({ status: 'PASS', results }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
