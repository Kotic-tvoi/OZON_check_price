// Minimal local smoke test for the Apps Script request shape (no Google account required).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync(__dirname + '/../google_sheets/Code.gs', 'utf8');
const values = new Map([
  ['A2', '380181277'], ['A3', '2624769265'],
  ['H2', 'https://www.ozon.ru/geo/moskva/442329/']
]);
const cellKey = (row, col) => String.fromCharCode(64 + col) + row;
const sheet = {
  getLastRow: () => 3,
  setFrozenRows: () => {},
  getRange: (r, c, nRows = 1, nCols = 1) => {
    let startRow = r, startCol = c;
    if (typeof r === 'string') {
      const match = /^([A-Z]+)(\d+)?(?::[A-Z]+)?$/.exec(r);
      assert.ok(match, r);
      startCol = match[1].charCodeAt(0) - 64;
      startRow = Number(match[2]) || 1;
      nRows = 1; nCols = 1;
    }
    return {
      getDisplayValue: () => String(values.get(cellKey(startRow, startCol)) || ''),
      getDisplayValues: () => Array.from({length: nRows}, (_, i) =>
        Array.from({length: nCols}, (_, j) => String(values.get(cellKey(startRow+i, startCol+j)) || ''))),
      setValue: value => {values.set(cellKey(startRow, startCol), value);},
      setValues: rows => rows.forEach((row, i) => row.forEach((v,j) => values.set(cellKey(startRow+i,startCol+j),v))),
      clearContent: () => {for(let i=0;i<nRows;i++)for(let j=0;j<nCols;j++) values.delete(cellKey(startRow+i,startCol+j));},
      setNumberFormat: () => {}
    };
  }
};
const documentProperties = new Map();
const calls = [];
let simulateBlock = false;
const context = {
  LockService: {getDocumentLock: () => ({tryLock: () => true, releaseLock: () => {}})},
  SpreadsheetApp: {
    getActive: () => ({getSheetByName: () => sheet}),
    getUi: () => ({alert: () => {}}),
    flush: () => {}
  },
  PropertiesService: {
    getDocumentProperties: () => ({
      setProperty: (k,v) => documentProperties.set(k,v),
      getProperty: k => documentProperties.get(k),
      deleteProperty: k => documentProperties.delete(k),
      setProperties: obj => Object.entries(obj).forEach(([k,v])=>documentProperties.set(k,v))
    }),
    getScriptProperties: () => ({
      getProperty: k => ({OZON_SERVER_URL:'https://prices.example.test', OZON_API_TOKEN:'test-token'})[k]
    })
  },
  UrlFetchApp: {fetch: (url, opts) => {
    const payload = JSON.parse(opts.payload);
    calls.push({url,payload});
    return {
      getContentText: () => JSON.stringify({pvz_url: payload.pvz_url, results: payload.articles.map((article,index) => ({
        article,price:simulateBlock && index === 1 ? null : 100+index, status:simulateBlock && index === 1 ? 'blocked' : 'ok'
      }))}),
      getResponseCode: () => 200
    };
  }}
};
vm.runInNewContext(code, context);
context.ozonStart();
assert.equal(calls.length, 1);
assert.equal(calls[0].url, 'https://prices.example.test/v1/prices');
assert.equal(calls[0].payload.pvz_url, 'https://www.ozon.ru/geo/moskva/442329/');
assert.deepEqual(Array.from(calls[0].payload.articles), ['380181277', '2624769265']);
assert.equal(Object.hasOwn(calls[0].payload,'items'), false);
assert.equal(values.get('B2'),100);
assert.equal(values.get('B3'),101);
assert.equal(values.get('C1'), undefined);
assert.equal(values.get('C2'), undefined);
assert.equal(values.get('A1'), 'Артикул товара');
assert.equal(values.get('B1'), 'Конечная цена');
assert.equal(values.get('H2'),'https://www.ozon.ru/geo/moskva/442329/');
console.log('Apps Script smoke test OK: one PVZ, 2 SKU, columns A/B only.');

// After a CAPTCHA the worksheet must pause, leaving the first blocked SKU as the next resume point.
simulateBlock = true;
context.ozonStart();
assert.equal(values.get('B2'), 100);
assert.equal(values.get('B3'), '');
assert.equal(documentProperties.get('OZON_PRICE_NEXT_ROW'), '3');
assert.equal(calls.length, 2);
console.log('Apps Script block/pause test OK: resumes at blocked row.');