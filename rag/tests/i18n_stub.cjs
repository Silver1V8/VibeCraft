// Stub IT di `t()` per i harness Node che evalano pezzi di pages/*.js senza i18n.js.
// Carica il catalogo italiano reale così le asserzioni sul testo restano valide.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const sandbox = { window: {} };
vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, '../static/i18n/messages.js'), 'utf8'),
  sandbox,
);
const catalog = sandbox.window.VIBECRAFT_MESSAGES.it;

function t(key, params) {
  let msg = catalog[key] ?? key;
  if (params && typeof params === 'object') {
    for (const [k, v] of Object.entries(params)) {
      msg = String(msg).split('{' + k + '}').join(String(v));
    }
  }
  return msg;
}

module.exports = { t, catalog };
