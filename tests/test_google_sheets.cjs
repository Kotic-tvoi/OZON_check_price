const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync(__dirname + '/../google_sheets/Code.gs', 'utf8');
const articles = Array.from({length: 100}, (_, i) => String(380000000 + i));
const values = new Map([['H2','https://www.ozon.ru/geo/moskva/442329/']]);
articles.forEach((v,i) => values.set(`A${i+2}`,v));
const colIndex = v => v.charCodeAt(0) - 64;
const key = (r,c) => `${String.fromCharCode(c+64)}${r}`;
const calls=[]; let blocked=false; let readRows=100;
const sheet={
  getLastRow:()=>readRows+1,
  setFrozenRows:()=>{},
  getRange:(r,c,nr=1,nc=1)=>{
    let row=r,col=c;
    if(typeof r==='string') {
      const m = /^([A-Z]+)(\d+)?(?::[A-Z]+)?$/.exec(r);
      assert.ok(m,r);
      col=colIndex(m[1]);row=Number(m[2])||1;nr=nc=1;
    }
    return {
      getDisplayValue:()=>String(values.get(key(row,col))||''),
      getDisplayValues:()=>Array.from({length:nr},(_,i)=>Array.from({length:nc},(_,j)=>String(values.get(key(row+i,col+j))||''))),
      setValue:(v)=>values.set(key(row,col),v),
      setValues:(rows)=>rows.forEach((arr,i)=>arr.forEach((v,j)=>values.set(key(row+i,col+j),v))),
      setNumberFormat:()=>{},
    }
  }
};
const context={
  LockService:{getDocumentLock:()=>({tryLock:()=>true,releaseLock:()=>{}})},
  SpreadsheetApp:{getActive:()=>({getSheetByName:()=>sheet}),getUi:()=>({alert:()=>{}})},
  PropertiesService:{getScriptProperties:()=>({getProperty:(k)=>({OZON_SERVER_URL:'https://prices.example.test',OZON_API_TOKEN:'token'})[k]})},
  UrlFetchApp:{fetch:(url,options)=>{
    const req=JSON.parse(options.payload);calls.push(req);
    return {getResponseCode:()=>200,getContentText:()=>JSON.stringify({pvz_url:req.pvz_url,results:req.articles.map((article,i)=>({article,price:blocked?null:i+10,status:blocked?'blocked':(i===2?'unavailable':'ok')}))})};
  }}
};
vm.runInNewContext(code,context);
context.ozonStart();
assert.equal(calls.length,1);
assert.equal(calls[0].articles.length,100);
assert.equal(values.get('B2'),10);
assert.equal(values.get('B3'),11);
assert.equal(values.get('B4'),'Нет данных');
assert.equal(values.get('B101'),109);
assert.equal(values.get('C1'),undefined);
assert.equal(values.get('H2'),'https://www.ozon.ru/geo/moskva/442329/');
blocked=true;
assert.throws(()=>context.ozonStart(),/ограничил доступ/);
assert.equal(values.get('B2'),10,'prior data is preserved after failed complete request');
blocked=false;
readRows=101;
values.set('A102','999999999');
assert.throws(()=>context.ozonStart(),/не более 100 SKU/);
assert.equal(calls.length,2,'oversized list must not call API');
console.log('PASS: one HTTP request for 100 SKUs; no batching; no-data rendering; atomic blocking; >100 rejected.');