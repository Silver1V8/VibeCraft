// Smoke layout: footer azioni Canvas sempre nel markup come review-actions;
// governance Propose demoted in details; niente max-height fissi che spingono Approva fuori.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '../templates/pipeline.unified.html'), 'utf8');
const js = fs.readFileSync(path.join(__dirname, '../static/pages/pipeline.js'), 'utf8');
const messages = fs.readFileSync(path.join(__dirname, '../static/i18n/messages.js'), 'utf8');

assert.match(html, /#panel-step-2\s*\{[^}]*overflow:\s*hidden/s);
assert.match(html, /\.review-stage\.flex\s*\{[^}]*overflow:\s*hidden/s);
assert.match(html, /\.review-stage\s+\.md-editor\s*\{[^}]*min-height:\s*0/s);
assert.match(html, /id="review-canvas"[^>]*review-stage/);
assert.match(html, /id="review-canvas"[\s\S]*?class="review-actions/);
assert.match(html, /id="review-explore"[^>]*review-stage/);
assert.doesNotMatch(html, /id="review-canvas"[^>]*style="[^"]*max-height/);
assert.doesNotMatch(html, /id="review-explore"[^>]*style="[^"]*max-height/);

assert.match(html, /id="panel-step-3"[^>]*propose-stage/);
assert.match(html, /id="final-prompt-card"[\s\S]*?id="validate-card"/);
assert.match(html, /id="validate-details-root"/);
assert.match(html, /id="gate-status-summary"/);
assert.match(html, /class="agent-run-bar"/);
assert.doesNotMatch(html, /id="final-prompt-box"[^>]*max-h-64/);

assert.match(js, /classList\.add\('is-approved'\)/);
assert.match(js, /dryrun-card'\)\.classList\.add\('is-compact'\)/);
assert.match(js, /gate-status-summary/);
assert.match(js, /gate-point-raw/);

for (const key of [
  'pipeline.review.approvedHint',
  'pipeline.validate.detailsSummary',
  'pipeline.validate.logSummary',
  'pipeline.validate.reportSummary',
]) {
  assert.match(messages, new RegExp(`'${key}':`));
}

console.log('Pipeline UI layout checks passed');
