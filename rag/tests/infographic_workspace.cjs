// Real Mermaid/layout in an initially hidden srcdoc frame; no live API or index writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'none'");
    if (url.pathname === '/api/health') {
      res.setHeader('Content-Type', 'application/json');
      return res.end(JSON.stringify({ status: 'ok', snapshot: {}, eval: {}, dependencies: {} }));
    }
    if (url.pathname === '/') {
      res.setHeader('Content-Type', 'text/html');
      return res.end('<!doctype html><html data-theme="matrix"><body></body></html>');
    }
    const file = url.pathname === '/infografica' ? path.join(root, 'templates/infografica.unified.html')
      : path.resolve(root, '.' + url.pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css'
      : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html');
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(async () => {
      const frame = document.createElement('iframe');
      frame.style.cssText = 'width:100%;height:850px;border:0';
      frame.dataset.workspacePage = '/infografica';
      frame.dataset.projectId = 'legacy';
      frame.hidden = true;
      frame.srcdoc = await (await fetch('/infografica')).text();
      await new Promise(resolve => {
        frame.addEventListener('load', resolve, { once: true });
        document.body.appendChild(frame);
      });
    });
    // Keep the cached page hidden through initial rendering and a theme change.
    await page.evaluate(() => document.querySelector('iframe').contentWindow.setUiTheme('classic'));
    await page.waitForTimeout(400);
    const hiddenState = await page.evaluate(() => {
      const doc = document.querySelector('iframe').contentDocument;
      return { content: doc.getElementById('rag-mermaid').textContent,
        orphan: [...doc.body.children].filter(el => el.id.startsWith('drag-mermaid-svg-')).map(el => el.textContent) };
    });
    assert.deepEqual(hiddenState, { content: '', orphan: [] }, 'Hidden frames must defer layout and leave no Mermaid errors');
    await page.evaluate(() => { document.querySelector('iframe').hidden = false; });
    const frame = page.frames().find(frame => frame.url() === 'about:srcdoc');
    async function assertDiagram(theme) {
      await frame.waitForFunction(() => document.querySelector('#rag-mermaid svg')?.querySelectorAll('.node').length === 12);
      await frame.waitForFunction(expected => {
        const node = document.querySelector('#rag-mermaid svg .node rect');
        return node && getComputedStyle(node).fill === expected;
      },
        theme === 'classic' ? 'rgb(226, 232, 240)' : 'rgb(4, 20, 10)');
      const geometry = await frame.locator('#rag-mermaid svg').evaluate(svg => ({
        width: svg.getBoundingClientRect().width, height: svg.getBoundingClientRect().height,
        labels: [...svg.querySelectorAll('.nodeLabel')].map(label => label.getBoundingClientRect().width),
        malformed: [...svg.querySelectorAll('[d]')].some(el => /NaN|Infinity/.test(el.getAttribute('d'))),
      }));
      assert.ok(geometry.width > 0 && geometry.height > 0 && geometry.labels.every(width => width > 0), JSON.stringify(geometry));
      assert.equal(geometry.malformed, false);
      assert.equal(await frame.locator('body > div[id^="drag-mermaid-svg-"]').count(), 0, 'No temporary Mermaid error diagram');
      assert.equal(await frame.locator('body').innerText().then(text => /Syntax error in text|Errore nel rendering/.test(text)), false);
    }
    await assertDiagram('classic');
    for (const theme of ['matrix', 'classic', 'matrix']) {
      await page.evaluate(theme => {
        const frame = document.querySelector('iframe');
        frame.hidden = true;
        frame.contentWindow.setUiTheme(theme);
      }, theme);
      await page.waitForTimeout(100);
      await page.evaluate(() => { document.querySelector('iframe').hidden = false; });
      await assertDiagram(theme);
    }
    await frame.evaluate(() => { setUiTheme('classic'); setUiTheme('matrix'); setUiTheme('classic'); });
    await assertDiagram('classic');
    // A real parser failure must stay in the diagram card, including Mermaid's scratch DOM.
    await frame.evaluate(async () => {
      const source = buildMermaidSource;
      buildMermaidSource = () => 'graph TD\nA["unterminated';
      await renderMermaidDiagram();
      buildMermaidSource = source;
    });
    assert.match(await frame.locator('#rag-mermaid').innerText(), /Errore nel rendering del diagramma/);
    assert.equal(await frame.locator('body > div[id^="drag-mermaid-svg-"]').count(), 0);
    await frame.evaluate(() => renderMermaidDiagram());
    await assertDiagram('classic');
    assert.deepEqual(errors, []);
    console.log('OK infographic: hidden srcdoc, nonzero SVG/labels, cached navigation, both themes, rapid flips, no orphan errors.');
  } finally {
    await browser.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
