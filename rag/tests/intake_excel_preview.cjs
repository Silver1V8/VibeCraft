// Il codice reale della preview inline (in /static/pages/intake.js, era nel template), senza browser né dipendenze.
// Uso: node tests/intake_excel_preview.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const template = fs.readFileSync(path.join(__dirname, '../static/pages/intake.js'), 'utf8');
// escapeHtml e inlineMd sono quelle di /static/shared.js, che la pagina carica in <head>.
const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8').replace(/\r\n/g, '\n');
const sharedFunction = name => shared.slice(shared.indexOf(`function ${name}(`),
  shared.indexOf('\n}\n', shared.indexOf(`function ${name}(`)) + 3);
const escapeCode = sharedFunction('escapeHtml') + sharedFunction('inlineMd');
const code = template.slice(template.indexOf('    function excelText('), template.indexOf('    function formatDate('));
const context = vm.createContext({});
vm.runInContext(escapeCode + code, context);

// Uscita di core/intake_excel.py: escape backslash, entità per gli spazi di bordo, <br> per LF.
const md = [
  '## Budget\\_ \\#',
  '',
  '### A7:E7',
  '',
  '| Riga | A | B | C | D | E |',
  '| --- | --- | --- | --- | --- | --- |',
  '| 7 | a\\|b | prima<br>seconda | \\<b\\>x\\</b\\> | &#32;NA&#32; | c:\\\\dati\\\\ |',
].join('\n');
const html = context.mdToHtml(md, true);
assert.ok(html.includes('<h2>Budget_ #</h2>'), html);
assert.ok(html.includes('<th scope="col">Riga</th><th scope="col">A</th>'), html);
// Cinque colonne di dati: il pipe escapato non divide la cella.
assert.ok(html.includes('<td>7</td><td>a|b</td><td>prima<br>seconda</td>'), html);
assert.ok(html.includes('<td>&lt;b&gt;x&lt;/b&gt;</td>'), html);   // markup della fonte = testo
assert.ok(html.includes('<td> NA </td>'), html);
assert.ok(html.includes('<td>c:\\dati\\</td>'), html);
// Un `<br>` scritto nella cella è testo, non un a capo.
assert.ok(context.mdToHtml('| Riga | A |\n| --- | --- |\n| 1 | \\<br\\> |', true).includes('<td>&lt;br&gt;</td>'));
// HTML grezzo non generato dal serializzatore: mai eseguito.
const hostile = context.mdToHtml('| Riga | A |\n| --- | --- |\n| 1 | <img src=x onerror=alert(1)> |', true);
assert.ok(!hostile.includes('<img'), hostile);
// Il Markdown non Excel resta sul renderer ordinario.
assert.ok(context.mdToHtml('# Titolo\n\n**testo**').includes('<strong>testo</strong>'));
// inlineMd condiviso (anche Analisi): il markup del contenuto resta testo anche dentro **…**.
assert.equal(context.inlineMd('**<img src=x onerror=alert(1)>** `a<b`'),
  '<strong>&lt;img src=x onerror=alert(1)&gt;</strong> <code>a&lt;b</code>');
console.log('Preview Excel: celle, colonne, a capo, escape e HTML della fonte non eseguito');
