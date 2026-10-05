// Real FastAPI/Qdrant fixture supplied by test_project_integration.py; no intercepted routes.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const [base, A, B, existingRoot] = process.argv.slice(2);
  const browser = await chromium.launch({ ...(process.platform === 'win32' ? { channel: 'msedge' } : {}), headless: true });
  try {
    const context = await browser.newContext();
    await context.addInitScript(() => localStorage.setItem('vibecraft-api-key', 'integration-fixture-key'));
    const page = await context.newPage();
    await page.goto(`${base}/?project=${A}`);
    await page.waitForFunction(id => document.getElementById('project-select')?.value === id, A);
    const frameA = page.frameLocator(`iframe[data-project-id="${A}"][data-workspace-page="/"]`);
    await frameA.locator('#question-input').fill('same question');
    await frameA.locator('#ask-btn').click();
    await frameA.locator('#answer-text').filter({ hasText: 'ALPHA_SENTINEL' }).waitFor();
    await page.locator('#project-select').selectOption(B);
    const frameB = page.frameLocator(`iframe[data-project-id="${B}"][data-workspace-page="/"]`);
    await frameB.locator('#question-input').fill('same question');
    await frameB.locator('#ask-btn').click();
    await frameB.locator('#answer-text').filter({ hasText: 'BETA_SENTINEL' }).waitFor();
    assert.equal(await frameB.locator('#answer-text').textContent(), 'BETA_SENTINEL');
    await page.locator('#project-select').selectOption(A);
    assert.equal(await frameA.locator('#question-input').inputValue(), 'same question');
    assert.equal(await frameA.locator('#answer-text').textContent(), 'ALPHA_SENTINEL');
    assert.equal(await page.locator('#project-select').inputValue(), A);
    await page.locator('#project-new').click();
    await page.locator('#project-input').fill('UI created');
    await page.locator('#project-input').press('Enter');
    await page.waitForFunction(() => document.getElementById('project-select').selectedOptions[0]?.textContent === 'UI created');
    await page.locator('#project-open').click();
    await page.locator('#project-input').fill(existingRoot);
    await page.locator('#project-submit').click();
    await page.waitForFunction(() => document.getElementById('project-select').selectedOptions[0]?.textContent === 'UI opened');
    console.log('PASS real HTTP browser selection A → B → A, same query and distinct Qdrant contexts');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
